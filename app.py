import html
import io
import re
from datetime import date

import pandas as pd
import streamlit as st
from supabase import create_client

# ---------------------------------------------------------------
# PENGATURAN DASAR
# ---------------------------------------------------------------
st.set_page_config(page_title="Hitung HPP", page_icon="🍽️", layout="centered")

BATAS_MARGIN = 30  # margin (%) di bawah angka ini ditandai merah
SATUAN = ["gram", "kg", "ml", "liter", "pcs", "butir", "bungkus"]


# ---------------------------------------------------------------
# SAMBUNGAN KE SUPABASE (kunci dibaca dari st.secrets)
# ---------------------------------------------------------------
try:
    # Satu sambungan per pengunjung (bukan dibagi bersama), supaya
    # status login tidak tercampur antar pengunjung.
    if "db" not in st.session_state:
        st.session_state["db"] = create_client(
            st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"]
        )
    db = st.session_state["db"]
except Exception:
    st.error(
        "Kunci Supabase belum terpasang. Isi dulu di menu Secrets "
        "(SUPABASE_URL dan SUPABASE_KEY), lalu muat ulang halaman."
    )
    st.stop()


def keluar(pesan=None):
    """Keluar akun: bersihkan status login lalu kembali ke halaman masuk."""
    try:
        db.auth.sign_out()
    except Exception:
        pass
    for k in ("login", "db"):
        st.session_state.pop(k, None)
    if pesan:
        st.session_state["info_login"] = pesan
    st.rerun()


def halaman_login():
    st.title("🍽️ Hitung HPP Menu")
    st.caption("Silakan masuk untuk membuka data usaha Anda.")
    if "info_login" in st.session_state:
        st.warning(st.session_state.pop("info_login"))
    with st.form("form_login"):
        email = st.text_input("Email")
        sandi = st.text_input("Kata sandi", type="password")
        masuk = st.form_submit_button("Masuk")
    if masuk:
        try:
            db.auth.sign_in_with_password({"email": email.strip(), "password": sandi})
            st.session_state["login"] = True
            st.rerun()
        except Exception:
            st.error("Email atau kata sandi salah.")
    st.stop()


# Gerbang: tanpa login, halaman di bawah ini tidak akan dijalankan
if not st.session_state.get("login"):
    halaman_login()


# ---------------------------------------------------------------
# FUNGSI BANTU
# ---------------------------------------------------------------
def ambil(tabel, kolom, angka=(), eq=None):
    """Ambil seluruh isi tabel sebagai DataFrame (tabel di memori)."""
    data = []
    mulai = 0
    while True:  # Supabase membatasi 1000 baris per permintaan, jadi ambil bertahap
        try:
            q = db.table(tabel).select("*")
            if eq:
                q = q.eq(eq[0], eq[1])
            bagian = q.order("id").range(mulai, mulai + 999).execute().data
        except Exception as e:
            if "jwt" in str(e).lower() or "expired" in str(e).lower():
                keluar("Sesi sudah habis, silakan masuk lagi.")
            raise
        data += bagian
        if len(bagian) < 1000:
            break
        mulai += 1000
    df = pd.DataFrame(data) if data else pd.DataFrame(columns=kolom)
    for k in angka:
        df[k] = pd.to_numeric(df[k])
    return df


def rp(x):
    return "Rp " + f"{x:,.0f}".replace(",", ".")


def sukses(pesan):
    st.session_state["pesan"] = pesan
    st.rerun()


def jalankan(aksi, pesan_sukses):
    try:
        aksi()
    except Exception as e:
        st.error(f"Gagal menyimpan: {e}")
        return
    sukses(pesan_sukses)


# ---------------------------------------------------------------
# AMBIL DATA TERBARU
# ---------------------------------------------------------------
bahan = ambil(
    "bahan",
    ["id", "nama_bahan", "satuan", "stok_saat_ini", "stok_minimum", "kode", "harga_standar"],
    ["id", "stok_saat_ini", "stok_minimum", "harga_standar"],
)
pembelian = ambil(
    "pembelian",
    ["id", "tanggal", "id_bahan", "jumlah", "total_harga", "supplier"],
    ["id", "id_bahan", "jumlah", "total_harga"],
)
menu = ambil(
    "menu",
    ["id", "nama_menu", "harga_jual", "jumlah_porsi_per_resep", "kode", "satuan_produk"],
    ["id", "harga_jual", "jumlah_porsi_per_resep"],
)
resep = ambil(
    "resep",
    ["id", "id_menu", "id_bahan", "jumlah_dipakai"],
    ["id", "id_menu", "id_bahan", "jumlah_dipakai"],
)

label_bahan = {f"{r.nama_bahan} ({r.satuan})": int(r.id) for r in bahan.itertuples()}
label_menu = {r.nama_menu: int(r.id) for r in menu.itertuples()}

# ---------------------------------------------------------------
# JUDUL, PESAN, DAN PERINGATAN STOK
# ---------------------------------------------------------------
st.title("🍽️ Hitung HPP Menu")

if "pesan" in st.session_state:
    st.success(st.session_state.pop("pesan"))

rendah = bahan[bahan["stok_saat_ini"] < bahan["stok_minimum"]]
if not rendah.empty:
    baris = [
        f"- **{r.nama_bahan}**: sisa {r.stok_saat_ini:g} {r.satuan} "
        f"(minimum {r.stok_minimum:g})"
        for r in rendah.itertuples()
    ]
    st.warning("⚠️ **Stok di bawah minimum:**\n" + "\n".join(baris))

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["📦 Bahan & Pembelian", "📖 Menu & Resep", "📊 Laporan", "📥 Impor Excel", "📸 Riwayat"]
)

# ---------------------------------------------------------------
# HALAMAN 1: BAHAN & PEMBELIAN
# ---------------------------------------------------------------
with tab1:
    st.subheader("Tambah bahan baru")
    with st.form("form_bahan", clear_on_submit=True):
        nama = st.text_input("Nama bahan", placeholder="Contoh: Tepung terigu")
        satuan = st.selectbox("Satuan", SATUAN)
        stok_awal = st.number_input(
            "Stok awal (isi 0 jika langsung input pembelian)", min_value=0.0, step=1.0
        )
        stok_min = st.number_input(
            "Stok minimum (batas peringatan)", min_value=0.0, step=1.0
        )
        kirim = st.form_submit_button("Simpan bahan")
    if kirim:
        if not nama.strip():
            st.error("Nama bahan wajib diisi.")
        else:
            jalankan(
                lambda: db.table("bahan")
                .insert(
                    {
                        "nama_bahan": nama.strip(),
                        "satuan": satuan,
                        "stok_saat_ini": stok_awal,
                        "stok_minimum": stok_min,
                    }
                )
                .execute(),
                f"Bahan '{nama.strip()}' tersimpan.",
            )

    st.divider()
    st.subheader("Catat pembelian")
    if bahan.empty:
        st.info("Tambah bahan dulu di atas, baru bisa mencatat pembelian.")
    else:
        with st.form("form_beli", clear_on_submit=True):
            pilih = st.selectbox("Bahan yang dibeli", list(label_bahan))
            tgl = st.date_input("Tanggal", value=date.today())
            jml = st.number_input("Jumlah dibeli (sesuai satuan)", min_value=0.0, step=1.0)
            total = st.number_input("Total harga (Rp)", min_value=0.0, step=1000.0)
            supplier = st.text_input("Supplier (boleh dikosongkan)")
            kirim = st.form_submit_button("Simpan pembelian")
        if kirim:
            if jml <= 0:
                st.error("Jumlah harus lebih dari 0.")
            else:
                id_b = label_bahan[pilih]
                stok_lama = float(
                    bahan.loc[bahan["id"] == id_b, "stok_saat_ini"].iloc[0]
                )

                def simpan_pembelian():
                    db.table("pembelian").insert(
                        {
                            "tanggal": str(tgl),
                            "id_bahan": id_b,
                            "jumlah": jml,
                            "total_harga": total,
                            "supplier": supplier.strip() or None,
                        }
                    ).execute()
                    db.table("bahan").update(
                        {"stok_saat_ini": stok_lama + jml}
                    ).eq("id", id_b).execute()

                jalankan(simpan_pembelian, "Pembelian tersimpan, stok sudah bertambah.")

    st.divider()
    st.subheader("Daftar bahan")
    if bahan.empty:
        st.caption("Belum ada bahan.")
    else:
        tampil = bahan[["nama_bahan", "satuan", "stok_saat_ini", "stok_minimum"]].rename(
            columns={
                "nama_bahan": "Bahan",
                "satuan": "Satuan",
                "stok_saat_ini": "Stok",
                "stok_minimum": "Minimum",
            }
        )
        st.dataframe(tampil, hide_index=True)

    st.subheader("Pembelian terakhir")
    if pembelian.empty:
        st.caption("Belum ada pembelian.")
    else:
        gabung = pembelian.merge(
            bahan[["id", "nama_bahan"]].rename(columns={"id": "id_bahan"}), on="id_bahan"
        ).sort_values(["tanggal", "id"], ascending=False)
        tampil = gabung.head(10)[
            ["tanggal", "nama_bahan", "jumlah", "total_harga", "supplier"]
        ].rename(
            columns={
                "tanggal": "Tanggal",
                "nama_bahan": "Bahan",
                "jumlah": "Jumlah",
                "total_harga": "Total (Rp)",
                "supplier": "Supplier",
            }
        )
        st.dataframe(tampil, hide_index=True)

# ---------------------------------------------------------------
# HALAMAN 2: MENU & RESEP
# ---------------------------------------------------------------
with tab2:
    st.subheader("Tambah menu baru")
    with st.form("form_menu", clear_on_submit=True):
        nama_m = st.text_input("Nama menu", placeholder="Contoh: Nasi goreng spesial")
        harga = st.number_input("Harga jual per porsi (Rp)", min_value=0.0, step=1000.0)
        porsi = st.number_input(
            "Satu resep menghasilkan berapa porsi?", min_value=1, step=1, value=1
        )
        kirim = st.form_submit_button("Simpan menu")
    if kirim:
        if not nama_m.strip():
            st.error("Nama menu wajib diisi.")
        else:
            jalankan(
                lambda: db.table("menu")
                .insert(
                    {
                        "nama_menu": nama_m.strip(),
                        "harga_jual": harga,
                        "jumlah_porsi_per_resep": int(porsi),
                    }
                )
                .execute(),
                f"Menu '{nama_m.strip()}' tersimpan.",
            )

    st.divider()
    st.subheader("Isi resep")
    if menu.empty or bahan.empty:
        st.info("Tambah minimal satu bahan dan satu menu dulu.")
    else:
        pilih_menu = st.selectbox("Pilih menu", list(label_menu))
        id_m = label_menu[pilih_menu]

        with st.form("form_resep", clear_on_submit=True):
            pilih_b = st.selectbox("Bahan", list(label_bahan))
            jml_pakai = st.number_input(
                "Jumlah dipakai untuk satu resep (sesuai satuan bahan)",
                min_value=0.0,
                step=1.0,
            )
            kirim = st.form_submit_button("Tambah ke resep")
        if kirim:
            if jml_pakai <= 0:
                st.error("Jumlah dipakai harus lebih dari 0.")
            else:
                jalankan(
                    lambda: db.table("resep")
                    .insert(
                        {
                            "id_menu": id_m,
                            "id_bahan": label_bahan[pilih_b],
                            "jumlah_dipakai": jml_pakai,
                        }
                    )
                    .execute(),
                    "Bahan masuk ke resep.",
                )

        st.markdown(f"**Resep: {pilih_menu}**")
        resep_menu = resep[resep["id_menu"] == id_m].merge(
            bahan[["id", "nama_bahan", "satuan"]].rename(columns={"id": "id_bahan"}),
            on="id_bahan",
        )
        if resep_menu.empty:
            st.caption("Resep masih kosong.")
        else:
            tampil = resep_menu[["nama_bahan", "jumlah_dipakai", "satuan"]].rename(
                columns={
                    "nama_bahan": "Bahan",
                    "jumlah_dipakai": "Jumlah",
                    "satuan": "Satuan",
                }
            )
            st.dataframe(tampil, hide_index=True)

            label_baris = {
                f"{r.nama_bahan} - {r.jumlah_dipakai:g} {r.satuan}": int(r.id)
                for r in resep_menu.itertuples()
            }
            with st.expander("Salah input? Hapus bahan dari resep"):
                hapus = st.selectbox("Pilih baris", list(label_baris))
                if st.button("Hapus baris ini"):
                    jalankan(
                        lambda: db.table("resep")
                        .delete()
                        .eq("id", label_baris[hapus])
                        .execute(),
                        "Baris resep dihapus.",
                    )

# ---------------------------------------------------------------
# HALAMAN 3: LAPORAN HPP & MARGIN
# ---------------------------------------------------------------
with tab3:
    st.subheader("Laporan HPP & margin")
    st.caption(
        f"Kartu merah = margin di bawah {BATAS_MARGIN}%. Urutan dari margin (%) terkecil."
    )

    if menu.empty:
        st.info("Belum ada menu. Tambahkan di halaman Menu & Resep, atau impor dari Excel.")
    else:
        sumber = st.radio(
            "Sumber harga bahan",
            ["Pembelian (jika ada), kalau belum ada pakai harga BOM", "Harga BOM saja"],
        )

        # harga rata-rata per satuan bahan = total uang / total jumlah dibeli
        sembunyi = st.checkbox("Sembunyikan menu tanpa harga jual", value=True)

        harga_beli = {}
        if not pembelian.empty:
            ringkas = pembelian.groupby("id_bahan")[["total_harga", "jumlah"]].sum()
            rata = ringkas["total_harga"] / ringkas["jumlah"]
            harga_beli = {int(k): float(v) for k, v in rata.items()}
        harga_bom = {
            int(r.id): float(r.harga_standar)
            for r in bahan.itertuples()
            if pd.notna(r.harga_standar)
        }
        if sumber.startswith("Harga BOM"):
            harga_satuan = harga_bom
        else:
            harga_satuan = {**harga_bom, **harga_beli}

        hasil = []
        for m in menu.itertuples():
            baris_resep = resep[resep["id_menu"] == m.id]
            biaya = 0.0
            ada_bahan_tanpa_harga = False
            for b in baris_resep.itertuples():
                h = harga_satuan.get(int(b.id_bahan))
                if h is None:
                    ada_bahan_tanpa_harga = True
                else:
                    biaya += b.jumlah_dipakai * h

            hpp = biaya / m.jumlah_porsi_per_resep
            margin_rp = m.harga_jual - hpp
            margin_pct = (margin_rp / m.harga_jual * 100) if m.harga_jual > 0 else 0

            catatan = []
            if baris_resep.empty:
                catatan.append("Resep belum diisi.")
            elif ada_bahan_tanpa_harga:
                catatan.append(
                    "Ada bahan tanpa harga (belum ada pembelian atau harga BOM), "
                    "HPP bisa terlalu kecil."
                )
            if m.harga_jual <= 0:
                catatan.append("Harga jual belum diisi.")

            satuan = (
                m.satuan_produk
                if isinstance(m.satuan_produk, str) and m.satuan_produk.strip()
                else "porsi"
            )
            kode_m = m.kode if isinstance(m.kode, str) else ""
            hasil.append(
                (m.nama_menu, kode_m, m.harga_jual, hpp, margin_rp, margin_pct, " ".join(catatan), satuan)
            )

        hasil.sort(key=lambda x: x[5])  # margin % terkecil di atas

        if sembunyi:
            n_tanpa_jual = sum(1 for x in hasil if x[2] <= 0)
            hasil = [x for x in hasil if x[2] > 0]
            if n_tanpa_jual:
                st.caption(f"{n_tanpa_jual} menu tanpa harga jual disembunyikan.")

        jumlah_merah = sum(1 for x in hasil if x[5] < BATAS_MARGIN)
        st.metric("Menu dengan margin rendah", f"{jumlah_merah} dari {len(hasil)}")

        cari = st.text_input("Cari menu", placeholder="Ketik sebagian nama atau kode menu")
        hanya_merah = st.checkbox(f"Hanya tampilkan margin di bawah {BATAS_MARGIN}%")
        batas_tampil = st.selectbox("Jumlah kartu ditampilkan", ["25", "50", "100", "Semua"])

        tampil = [
            x
            for x in hasil
            if (not cari or cari.lower() in f"{x[0]} {x[1]}".lower())
            and (not hanya_merah or x[5] < BATAS_MARGIN)
        ]
        total_cocok = len(tampil)
        if batas_tampil != "Semua":
            tampil = tampil[: int(batas_tampil)]
        st.caption(f"Menampilkan {len(tampil)} dari {total_cocok} menu.")

        for nama_m, kode_m, hj, hpp, mrp, mpct, catatan, satuan in tampil:
            merah = mpct < BATAS_MARGIN
            warna_bg = "#fdecea" if merah else "#eef7ee"
            warna_garis = "#d93025" if merah else "#2e7d32"
            teks_catatan = (
                f"<br><span style='font-size:0.85rem'>ℹ️ {html.escape(catatan)}</span>"
                if catatan
                else ""
            )
            teks_kode = (
                f" <span style='font-size:0.8rem;color:#666'>({html.escape(kode_m)})</span>"
                if kode_m
                else ""
            )
            kartu = (
                f"<div style='background:{warna_bg};border-left:6px solid {warna_garis};"
                f"padding:12px 14px;border-radius:10px;margin-bottom:10px;color:#222'>"
                f"<b style='font-size:1.05rem'>{html.escape(nama_m)}</b>{teks_kode}<br>"
                f"Harga jual: {rp(hj)}<br>"
                f"HPP per {html.escape(satuan)}: {rp(hpp)}<br>"
                f"Margin: <b>{rp(mrp)} ({mpct:.1f}%)</b>"
                f"{teks_catatan}</div>"
            )
            st.markdown(kartu, unsafe_allow_html=True)

# ---------------------------------------------------------------
# HALAMAN 4: IMPOR EXCEL (BOM)
# ---------------------------------------------------------------
TIDAK = "(tidak ada)"

# Tebakan nama judul kolom (huruf kecil, tanpa spasi dan simbol)
TEBAKAN = {
    "kode_menu": ["kodeproduk", "kodemenu"],
    "nama_menu": ["namaproduk", "namamenu"],
    "satuan_produk": ["uom", "satuan"],
    "yield": ["yield", "hasil"],
    "kode_bahan": ["kodebahan", "kodeprodukbahan", "kodematerial", "kodekomponen"],
    "satuan_bahan": ["uombahan", "satuanbahan"],
    "nama_bahan": ["namabahan", "namamaterial", "namakomponen"],
    "qty": ["qtyused", "qty", "jumlah"],
    "harga": ["harga", "price"],
    "harga_jual": ["hargajual", "jual", "sellingprice"],
}


def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def ke_teks(x):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return ""
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return str(x).strip()


def ke_angka(x):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace("Rp", "").replace("rp", "").replace(" ", "")
    if s == "" or s.lower() == "nan":
        return None
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", s):  # contoh teks "12.000" = dua belas ribu
        s = s.replace(".", "")
    elif "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def potong(daftar, n):
    for i in range(0, len(daftar), n):
        yield daftar[i : i + n]


def pertama(seri):
    for x in seri:
        if x:
            return x
    return ""


def siapkan(raw, peta, awal, isi_bawah=False):
    """Baca isi Excel jadi daftar menu, bahan, dan baris resep + daftar masalah."""
    n = len(raw)

    def kol(kunci, fungsi, kosong):
        k = peta[kunci]
        if k == TIDAK:
            return pd.Series([kosong] * n, index=raw.index)
        return raw[k].map(fungsi)

    d = pd.DataFrame(
        {
            "baris": raw.index + awal,
            "kode_menu": kol("kode_menu", ke_teks, ""),
            "nama_menu": kol("nama_menu", ke_teks, ""),
            "satuan_produk": kol("satuan_produk", ke_teks, ""),
            "yield_": kol("yield", ke_angka, None),
            "kode_bahan": kol("kode_bahan", ke_teks, ""),
            "nama_bahan": kol("nama_bahan", ke_teks, ""),
            "satuan_bahan": kol("satuan_bahan", ke_teks, ""),
            "qty": kol("qty", ke_angka, None),
            "harga": kol("harga", ke_angka, None),
            "harga_jual": kol("harga_jual", ke_angka, None),
        }
    )
    for k in ["yield_", "qty", "harga", "harga_jual"]:
        d[k] = pd.to_numeric(d[k], errors="coerce")

    masalah = []

    if isi_bawah:
        # Data produk hanya ada di baris pertama tiap produk: buang baris yang benar-benar
        # kosong, lalu isi kolom produk ke bawah, per blok produk.
        d = d[
            ~((d["nama_menu"] == "") & (d["nama_bahan"] == "") & (d["kode_bahan"] == "") & d["qty"].isna())
        ].copy()
        blok = (d["nama_menu"] != "").cumsum()
        for k in ["kode_menu", "nama_menu", "satuan_produk"]:
            d[k] = d[k].replace("", pd.NA).groupby(blok).ffill().fillna("")
        for k in ["yield_", "harga_jual"]:
            d[k] = d[k].groupby(blok).ffill()

    # baris kosong total dibuang diam-diam
    d = d[~((d["nama_menu"] == "") & (d["nama_bahan"] == ""))]

    salah_nama = (d["nama_menu"] == "") | (d["nama_bahan"] == "")
    for r in d[salah_nama].itertuples():
        masalah.append(("Baris dilewati", int(r.baris), "Nama menu atau nama bahan kosong"))
    d = d[~salah_nama]

    qty_salah = d["qty"].isna() | (d["qty"] <= 0)
    for r in d[qty_salah].itertuples():
        masalah.append(("Baris dilewati", int(r.baris), f"{r.nama_menu} / {r.nama_bahan}: qty kosong, bukan angka, atau 0"))
    d = d[~qty_salah].copy()

    d["km"] = [k if k else nm.lower() for k, nm in zip(d["kode_menu"], d["nama_menu"])]
    d["kb"] = [k if k else nb.lower() for k, nb in zip(d["kode_bahan"], d["nama_bahan"])]

    # ---- menu ----
    menus, menu_ok = [], set()
    for km, g in d.groupby("km", sort=False):
        nama = g["nama_menu"].iloc[0]
        baris0 = int(g["baris"].iloc[0])
        y = g["yield_"].dropna()
        y = y[y > 0]
        if y.empty:
            masalah.append(("Menu dilewati", baris0, f"{nama}: yield kosong atau 0"))
            continue
        if y.nunique() > 1:
            masalah.append(("Periksa", baris0, f"{nama}: yield berbeda antar baris ({y.min():g} sampai {y.max():g}), dipakai {y.iloc[0]:g}"))
        hj = g["harga_jual"].dropna()
        hj = hj[hj >= 0]
        if hj.nunique() > 1:
            masalah.append(("Periksa", baris0, f"{nama}: harga jual berbeda antar baris ({hj.min():g} sampai {hj.max():g}), dipakai {hj.iloc[0]:g}"))
        menus.append(
            {
                "key": km,
                "kode": pertama(g["kode_menu"]),
                "nama": nama,
                "satuan": pertama(g["satuan_produk"]),
                "yield": float(y.iloc[0]),
                "harga_jual": float(hj.iloc[0]) if not hj.empty else None,
            }
        )
        menu_ok.add(km)

    d = d[d["km"].isin(menu_ok)]

    # ---- baris resep ----
    resep_rows = []
    for (km, kb), g in d.groupby(["km", "kb"], sort=False):
        if len(g) > 1:
            masalah.append(("Periksa", int(g["baris"].iloc[0]), f"{g['nama_menu'].iloc[0]} / {g['nama_bahan'].iloc[0]}: bahan muncul {len(g)} kali, qty dijumlahkan"))
        resep_rows.append({"km": km, "kb": kb, "qty": float(g["qty"].sum())})

    # ---- bahan ----
    bahans = []
    for kb, g in d.groupby("kb", sort=False):
        nama = g["nama_bahan"].iloc[0]
        harga = g["harga"].dropna()
        harga = harga[harga >= 0]
        if harga.nunique() > 1:
            masalah.append(("Periksa", int(g["baris"].iloc[0]), f"{nama}: harga berbeda antar baris ({harga.min():g} sampai {harga.max():g}), dipakai harga terakhir {harga.iloc[-1]:g}"))
        bahans.append(
            {
                "key": kb,
                "kode": pertama(g["kode_bahan"]),
                "nama": nama,
                "satuan": pertama(g["satuan_bahan"]),
                "harga": float(harga.iloc[-1]) if not harga.empty else None,
            }
        )

    return menus, bahans, resep_rows, masalah, d


def simpan_impor(menus, bahans, resep_rows, ganti):
    """Simpan hasil bacaan Excel ke Supabase secara bertahap."""
    bar = st.progress(0.0, text="Menyimpan bahan...")
    for b in bahans:
        b["baru"] = b["id"] is None
    for m in menus:
        m["baru"] = m["id"] is None
    ada_b = {int(r.id): r for r in bahan.itertuples()}
    ada_m = {int(r.id): r for r in menu.itertuples()}

    # 1. bahan baru
    baru_b = [b for b in bahans if b["baru"]]
    for bagian in potong(baru_b, 200):
        rows = [
            {
                "kode": b["kode"] or None,
                "nama_bahan": b["nama"],
                "satuan": b["satuan"] or "unit",
                "stok_saat_ini": 0,
                "stok_minimum": 0,
                "harga_standar": b["harga"],
            }
            for b in bagian
        ]
        hasil_insert = db.table("bahan").insert(rows).execute().data
        for b, h in zip(bagian, hasil_insert):
            b["id"] = int(h["id"])

    # 2. bahan lama: perbarui harga standar dan kode jika perlu
    for b in bahans:
        if b["baru"]:
            continue
        lama = ada_b[b["id"]]
        ubah = {}
        if b["harga"] is not None and (pd.isna(lama.harga_standar) or float(lama.harga_standar) != b["harga"]):
            ubah["harga_standar"] = b["harga"]
        if b["kode"] and not (isinstance(lama.kode, str) and lama.kode):
            ubah["kode"] = b["kode"]
        if b["satuan"] and lama.satuan == "unit" and b["satuan"] != "unit":
            ubah["satuan"] = b["satuan"]
        if ubah:
            db.table("bahan").update(ubah).eq("id", b["id"]).execute()
    bar.progress(0.3, text="Menyimpan menu...")

    # 3. menu baru
    baru_m = [m for m in menus if m["baru"]]
    for bagian in potong(baru_m, 200):
        rows = [
            {
                "kode": m["kode"] or None,
                "nama_menu": m["nama"],
                "harga_jual": m["harga_jual"] if m["harga_jual"] is not None else 0,
                "jumlah_porsi_per_resep": m["yield"],
                "satuan_produk": m["satuan"] or None,
            }
            for m in bagian
        ]
        hasil_insert = db.table("menu").insert(rows).execute().data
        for m, h in zip(bagian, hasil_insert):
            m["id"] = int(h["id"])

    # 4. menu lama: perbarui hanya jika mode "Perbarui"
    lama_m = [m for m in menus if not m["baru"]]
    if ganti:
        for m in lama_m:
            lama = ada_m[m["id"]]
            ubah = {"jumlah_porsi_per_resep": m["yield"]}
            if m["satuan"]:
                ubah["satuan_produk"] = m["satuan"]
            if m["harga_jual"] is not None:
                ubah["harga_jual"] = m["harga_jual"]
            if m["kode"] and not (isinstance(lama.kode, str) and lama.kode):
                ubah["kode"] = m["kode"]
            db.table("menu").update(ubah).eq("id", m["id"]).execute()
    bar.progress(0.6, text="Menyimpan resep...")

    # 5. resep: hapus resep lama menu yang diperbarui, lalu isi dari Excel
    id_menu = {m["key"]: m["id"] for m in baru_m}
    if ganti:
        id_menu.update({m["key"]: m["id"] for m in lama_m})
        for bagian in potong([m["id"] for m in lama_m], 100):
            db.table("resep").delete().in_("id_menu", bagian).execute()
    id_bahan = {b["key"]: b["id"] for b in bahans}
    rows = [
        {"id_menu": id_menu[r["km"]], "id_bahan": id_bahan[r["kb"]], "jumlah_dipakai": r["qty"]}
        for r in resep_rows
        if r["km"] in id_menu
    ]
    for i, bagian in enumerate(potong(rows, 500)):
        db.table("resep").insert(bagian).execute()
    bar.progress(1.0, text="Selesai")
    return len(baru_b), len(baru_m), len(rows)


def halaman_impor(berkas):
    try:
        xls = pd.ExcelFile(berkas)
    except Exception:
        st.error("Berkas tidak bisa dibaca. Pastikan formatnya .xlsx dan tidak diberi kata sandi.")
        return

    sheet = st.selectbox("Pilih sheet", xls.sheet_names)
    hdr = st.number_input("Judul kolom ada di baris ke", min_value=1, value=1, step=1)
    raw = pd.read_excel(xls, sheet_name=sheet, header=int(hdr) - 1, dtype=object)
    raw = raw.dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)
    raw.columns = [str(c).strip() for c in raw.columns]
    kolom = list(raw.columns)

    if raw.empty or not kolom:
        st.warning("Sheet ini kosong atau judul kolomnya tidak ditemukan. Coba ubah nomor baris judul.")
        return

    st.caption("Isi sheet yang terbaca (judul kolom dan 5 baris pertama). Pastikan ini tabel BOM Anda:")
    st.dataframe(raw.head(5), hide_index=True)

    def tebak(kunci):
        for cand in TEBAKAN[kunci]:
            for k in kolom:
                if norm(k) == cand:
                    return k
            for k in kolom:
                n_k = norm(k)
                if cand in n_k and not (kunci == "harga" and "jual" in n_k):
                    return k
        return None

    WAJIB = [
        ("nama_menu", "Nama menu / produk"),
        ("yield", "Yield (jumlah hasil per resep)"),
        ("nama_bahan", "Nama bahan"),
        ("qty", "Qty dipakai"),
    ]
    OPSIONAL = [
        ("kode_menu", "Kode menu / produk"),
        ("satuan_produk", "Satuan produk jadi (uom)"),
        ("kode_bahan", "Kode bahan"),
        ("satuan_bahan", "Satuan bahan (uom bahan)"),
        ("harga", "Harga per satuan bahan"),
        ("harga_jual", "Harga jual menu"),
    ]
    peta = {}
    with st.expander("Pemetaan kolom (periksa, ubah jika perlu)", expanded=True):
        for kunci, label in WAJIB:
            tebakan = tebak(kunci)
            idx = kolom.index(tebakan) if tebakan in kolom else 0
            peta[kunci] = st.selectbox(
                label, kolom, index=idx, key=f"peta_{kunci}_{berkas.name}_{sheet}_{hdr}"
            )
        for kunci, label in OPSIONAL:
            opsi = [TIDAK] + kolom
            tebakan = tebak(kunci)
            idx = opsi.index(tebakan) if tebakan in opsi else 0
            peta[kunci] = st.selectbox(
                label + " (opsional)", opsi, index=idx, key=f"peta_{kunci}_{berkas.name}_{sheet}_{hdr}"
            )

    if len({peta[k] for k, _ in WAJIB}) < len(WAJIB):
        st.error(
            "Nama menu, yield, nama bahan, dan qty masih memakai kolom yang sama, "
            "jadi pembacaan belum benar. Periksa pilihan sheet dan nomor baris judul di atas, "
            "atau pilih kolomnya satu per satu di Pemetaan kolom."
        )
        return

    awal = int(hdr) + 1  # nomor baris Excel untuk data pertama

    # Banyak BOM hanya mengisi data produk di baris pertama tiap produk
    menu_kosong = raw[peta["nama_menu"]].map(ke_teks) == ""
    ada_bahan = raw[peta["nama_bahan"]].map(ke_teks) != ""
    pola = bool((menu_kosong & ada_bahan).any())
    isi_bawah = st.checkbox(
        "Data produk (kode, nama, yield, uom, harga jual) hanya terisi di baris pertama tiap produk. "
        "Isi otomatis ke baris di bawahnya.",
        value=pola,
        key=f"isibawah_{berkas.name}_{sheet}_{hdr}_{pola}",
    )
    menus, bahans, resep_rows, masalah, d = siapkan(raw, peta, awal, isi_bawah)

    # cocokkan dengan data yang sudah ada di aplikasi
    b_kode = {r.kode: int(r.id) for r in bahan.itertuples() if isinstance(r.kode, str) and r.kode}
    b_nama = {r.nama_bahan.strip().lower(): int(r.id) for r in bahan.itertuples()}
    m_kode = {r.kode: int(r.id) for r in menu.itertuples() if isinstance(r.kode, str) and r.kode}
    m_nama = {r.nama_menu.strip().lower(): int(r.id) for r in menu.itertuples()}
    for b in bahans:
        b["id"] = b_kode.get(b["kode"]) if b["kode"] else None
        if b["id"] is None:
            b["id"] = b_nama.get(b["nama"].lower())
    for m in menus:
        m["id"] = m_kode.get(m["kode"]) if m["kode"] else None
        if m["id"] is None:
            m["id"] = m_nama.get(m["nama"].lower())

    st.markdown("**Pratinjau**")
    menu_baru = sum(1 for m in menus if m["id"] is None)
    bahan_baru = sum(1 for b in bahans if b["id"] is None)
    tanpa_harga = sum(1 for b in bahans if b["harga"] is None)
    st.dataframe(
        pd.DataFrame(
            [
                ["Menu", len(menus), menu_baru, len(menus) - menu_baru],
                ["Bahan", len(bahans), bahan_baru, len(bahans) - bahan_baru],
                ["Baris resep", len(resep_rows), "", ""],
            ],
            columns=["Data", "Terbaca", "Baru", "Sudah ada"],
        ),
        hide_index=True,
    )
    if tanpa_harga:
        st.warning(f"{tanpa_harga} bahan tidak punya harga di Excel, HPP menu terkait bisa terlalu kecil.")
    if any(m["harga_jual"] is None for m in menus):
        st.caption("Menu tanpa harga jual akan disimpan dengan harga 0 dan bisa diisi nanti.")

    if not d.empty:
        contoh = d.head(8)[["baris", "nama_menu", "yield_", "nama_bahan", "qty", "harga", "harga_jual"]].rename(
            columns={
                "baris": "Baris Excel",
                "nama_menu": "Menu",
                "yield_": "Yield",
                "nama_bahan": "Bahan",
                "qty": "Qty",
                "harga": "Harga",
                "harga_jual": "Harga jual",
            }
        )
        st.caption("Contoh hasil pembacaan (cocokkan dengan Excel Anda):")
        st.dataframe(contoh, hide_index=True)

    if masalah:
        st.warning(f"Ada {len(masalah)} catatan untuk diperiksa.")
        st.dataframe(
            pd.DataFrame(masalah, columns=["Jenis", "Baris Excel", "Keterangan"]).head(200),
            hide_index=True,
        )

    mode = st.radio(
        "Jika menu sudah ada di aplikasi",
        [
            "Perbarui: ganti resep lama dengan versi Excel",
            "Lewati: biarkan menu yang sudah ada",
        ],
    )
    ganti = mode.startswith("Perbarui")
    siap = len(resep_rows) > 0
    if not siap:
        st.error("Belum ada baris resep yang valid. Periksa pemetaan kolom di atas.")
    if st.button("Simpan semua ke database", type="primary", disabled=not siap):
        try:
            n_b, n_m, n_r = simpan_impor(menus, bahans, resep_rows, ganti)
        except Exception as e:
            st.error(
                f"Impor terhenti: {e}. Data yang sudah masuk aman. "
                "Anda bisa mengulang impor yang sama dengan mode Perbarui."
            )
        else:
            sukses(f"Impor selesai: {n_b} bahan baru, {n_m} menu baru, {n_r} baris resep disimpan.")


with tab4:
    st.subheader("Impor BOM dari Excel")
    st.caption(
        "Unggah berkas BOM (.xlsx). Aplikasi membaca isinya, menampilkan pratinjau, "
        "dan baru menyimpan setelah Anda klik tombol Simpan."
    )
    berkas = st.file_uploader("Berkas BOM", type=["xlsx"])
    if berkas is None:
        st.info("Belum ada berkas. Siapkan Excel dengan satu baris judul kolom di atas datanya.")
    else:
        halaman_impor(berkas)

# ---------------------------------------------------------------
# HALAMAN 5: RIWAYAT HPP BULANAN (SNAPSHOT)
# ---------------------------------------------------------------
SUMBER_PEMBELIAN = "Pembelian (jika ada), kalau belum ada pakai harga BOM"
SUMBER_BOM = "Harga BOM saja"

KOL_SNAP = ["id", "periode", "catatan", "sumber_harga", "dibuat_pada"]
KOL_SM = ["id", "id_snapshot", "kunci", "kode", "nama_menu", "satuan_produk",
          "harga_jual", "jumlah_porsi", "hpp", "tanpa_harga"]
ANGKA_SM = ["id", "id_snapshot", "harga_jual", "jumlah_porsi", "hpp"]
KOL_SR = ["id", "id_snapshot", "id_snapshot_menu", "kunci_bahan", "kode_bahan",
          "nama_bahan", "satuan", "jumlah_dipakai", "harga_satuan"]
ANGKA_SR = ["id", "id_snapshot", "id_snapshot_menu", "jumlah_dipakai", "harga_satuan"]


def teks_atau_kosong(x):
    return x if isinstance(x, str) else ""


def harga_aktif(bom_saja):
    """Harga per satuan tiap bahan: rata-rata pembelian (jika ada) atau harga BOM."""
    harga_beli = {}
    if not pembelian.empty:
        ringkas = pembelian.groupby("id_bahan")[["total_harga", "jumlah"]].sum()
        rata = ringkas["total_harga"] / ringkas["jumlah"]
        harga_beli = {int(k): float(v) for k, v in rata.items()}
    harga_bom = {
        int(r.id): float(r.harga_standar) for r in bahan.itertuples() if pd.notna(r.harga_standar)
    }
    return harga_bom if bom_saja else {**harga_bom, **harga_beli}


def susun_snapshot(bom_saja):
    """Hitung HPP semua menu yang punya resep, lengkap dengan rincian bahannya."""
    harga = harga_aktif(bom_saja)
    info_bahan = {int(r.id): r for r in bahan.itertuples()}
    hasil = []
    for m in menu.itertuples():
        baris_resep = resep[resep["id_menu"] == m.id]
        if baris_resep.empty:
            continue
        kode_m = teks_atau_kosong(m.kode)
        biaya, tanpa, baris = 0.0, False, []
        for b in baris_resep.itertuples():
            ib = info_bahan.get(int(b.id_bahan))
            if ib is None:
                continue
            h = harga.get(int(b.id_bahan))
            if h is None:
                tanpa = True
            else:
                biaya += float(b.jumlah_dipakai) * h
            kode_b = teks_atau_kosong(ib.kode)
            baris.append(
                {
                    "kunci_bahan": kode_b or ib.nama_bahan.strip().lower(),
                    "kode_bahan": kode_b or None,
                    "nama_bahan": ib.nama_bahan,
                    "satuan": ib.satuan,
                    "jumlah_dipakai": float(b.jumlah_dipakai),
                    "harga_satuan": h,
                }
            )
        porsi = float(m.jumlah_porsi_per_resep)
        hasil.append(
            {
                "kunci": kode_m or m.nama_menu.strip().lower(),
                "kode": kode_m or None,
                "nama_menu": m.nama_menu,
                "satuan_produk": teks_atau_kosong(m.satuan_produk) or None,
                "harga_jual": float(m.harga_jual),
                "jumlah_porsi": porsi,
                "hpp": biaya / porsi,
                "tanpa_harga": tanpa,
                "baris": baris,
            }
        )
    return hasil


def simpan_snapshot(periode, catatan, bom_saja, timpa):
    menus_s = susun_snapshot(bom_saja)
    if not menus_s:
        raise ValueError("Belum ada menu yang memiliki resep.")
    bar = st.progress(0.0, text="Menyimpan snapshot...")
    sumber = SUMBER_BOM if bom_saja else SUMBER_PEMBELIAN
    kepala = (
        db.table("snapshot")
        .insert({"periode": periode, "catatan": catatan or None, "sumber_harga": sumber})
        .execute()
        .data[0]
    )
    id_s = int(kepala["id"])
    try:
        for bagian in potong(menus_s, 200):
            rows = [
                {
                    "id_snapshot": id_s,
                    "kunci": m["kunci"],
                    "kode": m["kode"],
                    "nama_menu": m["nama_menu"],
                    "satuan_produk": m["satuan_produk"],
                    "harga_jual": m["harga_jual"],
                    "jumlah_porsi": m["jumlah_porsi"],
                    "hpp": m["hpp"],
                    "tanpa_harga": m["tanpa_harga"],
                }
                for m in bagian
            ]
            keluar_rows = db.table("snapshot_menu").insert(rows).execute().data
            for m, h in zip(bagian, keluar_rows):
                m["id_sm"] = int(h["id"])
        bar.progress(0.5, text="Menyimpan rincian bahan...")
        baris_semua = [
            {"id_snapshot": id_s, "id_snapshot_menu": m["id_sm"], **b}
            for m in menus_s
            for b in m["baris"]
        ]
        for bagian in potong(baris_semua, 500):
            db.table("snapshot_resep").insert(bagian).execute()
    except Exception:
        try:  # batalkan snapshot yang belum lengkap
            db.table("snapshot").delete().eq("id", id_s).execute()
        except Exception:
            pass
        raise
    if timpa:  # snapshot baru sudah lengkap, baru hapus yang lama pada periode yang sama
        db.table("snapshot").delete().eq("periode", periode).neq("id", id_s).execute()
    bar.progress(1.0, text="Selesai")
    return len(menus_s), len(baris_semua)


@st.cache_data(ttl=300, show_spinner=False)
def muat_snapshot(id_s):
    sm = ambil("snapshot_menu", KOL_SM, ANGKA_SM, eq=("id_snapshot", id_s))
    sr = ambil("snapshot_resep", KOL_SR, ANGKA_SR, eq=("id_snapshot", id_s))
    return sm, sr


def kumpulkan(sm, sr):
    """Susun satu snapshot: menu per kunci, dan bahan per menu."""
    menus_k = {}
    for r in sm.itertuples():
        menus_k[r.kunci] = {
            "id": int(r.id),
            "kode": teks_atau_kosong(r.kode),
            "nama": r.nama_menu,
            "hj": float(r.harga_jual),
            "porsi": float(r.jumlah_porsi),
            "hpp": float(r.hpp),
        }
    bahan_per_menu = {}
    for r in sr.itertuples():
        harga = None if pd.isna(r.harga_satuan) else float(r.harga_satuan)
        d = bahan_per_menu.setdefault(int(r.id_snapshot_menu), {})
        e = d.get(r.kunci_bahan)
        if e is None:
            d[r.kunci_bahan] = {"nama": r.nama_bahan, "q": float(r.jumlah_dipakai), "p": harga}
        else:
            e["q"] += float(r.jumlah_dipakai)
            if e["p"] is None:
                e["p"] = harga
    return menus_k, bahan_per_menu


def beda(x, y):
    return abs(x - y) > 1e-9 * max(1.0, abs(x), abs(y))


def bandingkan(a, b):
    """Bandingkan dua snapshot. Selisih HPP dipecah menjadi efek harga dan efek komposisi."""
    menus_a, bpm_a = a
    menus_b, bpm_b = b
    kunci_semua = list(menus_b) + [k for k in menus_a if k not in menus_b]
    baris_utama, rincian = [], {}
    for kunci in kunci_semua:
        ma, mb = menus_a.get(kunci), menus_b.get(kunci)
        la = bpm_a.get(ma["id"], {}) if ma else {}
        lb = bpm_b.get(mb["id"], {}) if mb else {}
        ya = ma["porsi"] if ma else 1.0
        yb = mb["porsi"] if mb else 1.0
        e_harga = e_komp = 0.0
        detail = []
        for kb in list(lb) + [k for k in la if k not in lb]:
            x, y = la.get(kb), lb.get(kb)
            if x and y:
                pa, pb = x["p"] or 0.0, y["p"] or 0.0
                qa, qb = x["q"] / ya, y["q"] / yb
                d_q, d_p = (qb - qa) * pa, (pb - pa) * qb
                e_komp += d_q
                e_harga += d_p
                ubah_q, ubah_p = beda(qa, qb), beda(pa, pb)
                jenis = (
                    "Jumlah dan harga berubah" if ubah_q and ubah_p
                    else "Jumlah berubah" if ubah_q
                    else "Harga berubah" if ubah_p
                    else "Tetap"
                )
                detail.append([y["nama"], jenis, x["q"], y["q"], x["p"], y["p"], d_q + d_p])
            elif y:
                d = y["q"] / yb * (y["p"] or 0.0)
                e_komp += d
                detail.append([y["nama"], "Bahan baru", None, y["q"], None, y["p"], d])
            else:
                d = -x["q"] / ya * (x["p"] or 0.0)
                e_komp += d
                detail.append([x["nama"], "Bahan dihapus", x["q"], None, x["p"], None, d])

        if ma and mb:
            selisih = mb["hpp"] - ma["hpp"]
            persen = selisih / ma["hpp"] * 100 if ma["hpp"] > 0 else None
            status = "Tetap" if abs(selisih) < 0.005 else ("Naik" if selisih > 0 else "Turun")
        else:
            selisih = persen = None
            status = "Baru" if mb else "Dihapus"
        ref = mb or ma
        margin = (mb["hj"] - mb["hpp"]) / mb["hj"] * 100 if mb and mb["hj"] > 0 else None
        baris_utama.append(
            {
                "Menu": ref["nama"],
                "Kode": ref["kode"],
                "Status": status,
                "HPP lama": ma["hpp"] if ma else None,
                "HPP baru": mb["hpp"] if mb else None,
                "Selisih (Rp)": selisih,
                "Selisih (%)": persen,
                "Efek harga": e_harga if ma and mb else None,
                "Efek komposisi": e_komp if ma and mb else None,
                "Harga jual": mb["hj"] if mb else None,
                "Margin baru (%)": margin,
                "_kunci": kunci,
            }
        )
        rincian[kunci] = pd.DataFrame(
            detail,
            columns=["Bahan", "Perubahan", "Qty lama", "Qty baru", "Harga lama", "Harga baru", "Dampak ke HPP (Rp)"],
        )
    df = pd.DataFrame(baris_utama)
    df = df.sort_values("Selisih (Rp)", ascending=False, na_position="last").reset_index(drop=True)
    return df, rincian


def buat_excel(df, rincian, info):
    """Buat berkas Excel perbandingan dengan header rapi."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    font_isi = Font(name="DM Sans", size=10)
    font_head = Font(name="DM Sans", size=10, bold=True, color="1F2937")
    isi_head = PatternFill("solid", fgColor="E5E7EB")
    garis = Border(bottom=Side(style="thin", color="9CA3AF"))

    def tulis_tabel(ws, kolom, baris, format_angka):
        ws.append(kolom)
        for c in ws[1]:
            c.font, c.fill, c.border = font_head, isi_head, garis
            c.alignment = Alignment(vertical="center", wrap_text=True)
        for r in baris:
            ws.append([None if (isinstance(v, float) and pd.isna(v)) else v for v in r])
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.font = font_isi
                if isinstance(c.value, float):
                    c.number_format = format_angka
        for i, k in enumerate(kolom, start=1):
            lebar = max([len(str(k))] + [len(str(r[i - 1])) for r in baris[:200] if r[i - 1] is not None])
            ws.column_dimensions[get_column_letter(i)].width = min(max(lebar + 2, 10), 42)
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        ws.row_dimensions[1].height = 22

    wb = Workbook()
    ws0 = wb.active
    ws0.title = "Ringkasan"
    for label, nilai in info:
        ws0.append([label, nilai])
    for row in ws0.iter_rows():
        row[0].font = font_head
        row[1].font = font_isi
    ws0.column_dimensions["A"].width = 28
    ws0.column_dimensions["B"].width = 60

    kolom_utama = [c for c in df.columns if c != "_kunci"]
    ws1 = wb.create_sheet("Perbandingan")
    tulis_tabel(ws1, kolom_utama, df[kolom_utama].values.tolist(), "#,##0.00")

    ws2 = wb.create_sheet("Rincian Bahan")
    baris_r = []
    for _, r in df.iterrows():
        if r["Status"] == "Tetap":
            continue
        for x in rincian[r["_kunci"]].values.tolist():
            if x[1] != "Tetap":
                baris_r.append([r["Menu"], r["Kode"], *x])
    tulis_tabel(
        ws2,
        ["Menu", "Kode", "Bahan", "Perubahan", "Qty lama", "Qty baru", "Harga lama", "Harga baru", "Dampak ke HPP (Rp)"],
        baris_r,
        "#,##0.00",
    )
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


with tab5:
    st.subheader("Riwayat HPP bulanan")
    st.caption(
        "Snapshot adalah foto HPP semua menu pada satu bulan. Simpan setiap kali BOM selesai "
        "direvisi, lalu bandingkan antar bulan."
    )

    try:
        snaps = ambil("snapshot", KOL_SNAP, ["id"])
        tabel_snap_ada = True
    except Exception as e:
        tabel_snap_ada = False
        st.warning(
            "Tabel snapshot belum bisa dibaca. Pastikan SQL Tahap A sudah dijalankan di Supabase, "
            "lalu muat ulang halaman."
        )
        st.caption(f"Detail teknis: {e}")

    if tabel_snap_ada:
        # ---------- simpan snapshot ----------
        st.markdown("**Simpan snapshot**")
        periode = st.text_input(
            "Periode (tahun-bulan)", value=date.today().strftime("%Y-%m"), key="snap_periode"
        ).strip()
        catatan_s = st.text_input(
            "Catatan (opsional)", placeholder="Contoh: Revisi BOM setelah kenaikan harga tepung", key="snap_catatan"
        ).strip()
        sumber_s = st.radio("Sumber harga untuk snapshot", [SUMBER_PEMBELIAN, SUMBER_BOM], key="snap_sumber")
        periode_ok = bool(re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", periode))
        if not periode_ok:
            st.error("Format periode harus tahun-bulan, misalnya 2026-11.")
        sudah_ada = periode_ok and bool((snaps["periode"] == periode).any())
        timpa = False
        if sudah_ada:
            st.warning(f"Snapshot periode {periode} sudah ada.")
            timpa = st.checkbox("Timpa dengan kondisi terbaru", key="snap_timpa")
        n_menu_resep = int(resep["id_menu"].nunique()) if not resep.empty else 0
        st.caption(f"Akan menyimpan {n_menu_resep} menu yang memiliki resep.")
        bisa = periode_ok and (not sudah_ada or timpa) and n_menu_resep > 0
        if st.button("Simpan snapshot sekarang", type="primary", disabled=not bisa, key="snap_simpan"):
            try:
                n_m, n_r = simpan_snapshot(periode, catatan_s, sumber_s == SUMBER_BOM, timpa)
            except Exception as e:
                st.error(f"Snapshot gagal disimpan: {e}. Silakan coba lagi.")
            else:
                muat_snapshot.clear()
                sukses(f"Snapshot {periode} tersimpan: {n_m} menu, {n_r} baris bahan.")

        # ---------- daftar snapshot ----------
        st.divider()
        st.markdown("**Daftar snapshot**")
        if snaps.empty:
            st.caption("Belum ada snapshot.")
        else:
            snaps = snaps.sort_values(["periode", "id"], ascending=False)
            tampil_s = pd.DataFrame(
                {
                    "Periode": snaps["periode"],
                    "Dibuat": snaps["dibuat_pada"].astype(str).str[:16].str.replace("T", " "),
                    "Sumber harga": snaps["sumber_harga"],
                    "Catatan": snaps["catatan"],
                }
            )
            st.dataframe(tampil_s, hide_index=True)
            label_s = {
                f"{r.periode} (#{int(r.id)}, dibuat {str(r.dibuat_pada)[:10]})": int(r.id)
                for r in snaps.itertuples()
            }
            with st.expander("Hapus snapshot"):
                pilih_hapus = st.selectbox("Pilih snapshot", list(label_s), key="snap_hapus")
                yakin = st.checkbox("Saya yakin, snapshot ini akan hilang permanen", key="snap_yakin")
                if st.button("Hapus snapshot ini", disabled=not yakin, key="snap_btn_hapus"):
                    muat_snapshot.clear()
                    jalankan(
                        lambda: db.table("snapshot").delete().eq("id", label_s[pilih_hapus]).execute(),
                        "Snapshot dihapus.",
                    )

            # ---------- bandingkan ----------
            st.divider()
            st.markdown("**Bandingkan dua snapshot**")
            if len(snaps) < 2:
                st.info("Perlu minimal dua snapshot untuk membandingkan.")
            else:
                opsi = list(label_s)
                lama = st.selectbox("Snapshot lama (pembanding)", opsi, index=1, key="cmp_lama")
                baru = st.selectbox("Snapshot baru", opsi, index=0, key="cmp_baru")
                if lama == baru:
                    st.warning("Pilih dua snapshot yang berbeda.")
                else:
                    id_lama, id_baru = label_s[lama], label_s[baru]
                    sumber_map = {int(r.id): r.sumber_harga for r in snaps.itertuples()}
                    if sumber_map[id_lama] != sumber_map[id_baru]:
                        st.warning(
                            "Kedua snapshot memakai sumber harga yang berbeda, jadi selisih HPP "
                            "ikut dipengaruhi perbedaan itu."
                        )
                    df_cmp, rincian = bandingkan(
                        kumpulkan(*muat_snapshot(id_lama)), kumpulkan(*muat_snapshot(id_baru))
                    )
                    hitung = df_cmp["Status"].value_counts().to_dict()
                    st.markdown(
                        f"**{hitung.get('Naik', 0)}** menu naik, **{hitung.get('Turun', 0)}** turun, "
                        f"**{hitung.get('Tetap', 0)}** tetap, **{hitung.get('Baru', 0)}** baru, "
                        f"**{hitung.get('Dihapus', 0)}** dihapus."
                    )
                    f_status = st.selectbox(
                        "Tampilkan", ["Semua", "Naik", "Turun", "Tetap", "Baru", "Dihapus"], key="cmp_status"
                    )
                    f_cari = st.text_input("Cari menu", placeholder="Nama atau kode menu", key="cmp_cari")
                    df_tampil = df_cmp
                    if f_status != "Semua":
                        df_tampil = df_tampil[df_tampil["Status"] == f_status]
                    if f_cari:
                        gabung_teks = (df_tampil["Menu"] + " " + df_tampil["Kode"]).str.lower()
                        df_tampil = df_tampil[gabung_teks.str.contains(f_cari.lower(), regex=False)]
                    kolom_angka = ["HPP lama", "HPP baru", "Selisih (Rp)", "Efek harga", "Efek komposisi", "Harga jual"]
                    konfigurasi = {c: st.column_config.NumberColumn(c, format="%.2f") for c in kolom_angka}
                    konfigurasi["Selisih (%)"] = st.column_config.NumberColumn("Selisih (%)", format="%.1f")
                    konfigurasi["Margin baru (%)"] = st.column_config.NumberColumn("Margin baru (%)", format="%.1f")
                    st.caption(
                        f"Menampilkan {len(df_tampil)} dari {len(df_cmp)} menu, diurutkan dari kenaikan HPP terbesar. "
                        "Efek harga = dampak perubahan harga bahan. Efek komposisi = dampak bahan ditambah, "
                        "dibuang, atau jumlahnya berubah."
                    )
                    st.dataframe(
                        df_tampil.drop(columns="_kunci"), hide_index=True, column_config=konfigurasi
                    )

                    # penyebab perubahan per menu
                    adaperubahan = df_tampil[df_tampil["Status"].isin(["Naik", "Turun", "Tetap"])]
                    if not adaperubahan.empty:
                        label_menu_cmp = {
                            (f"{r['Menu']} ({r['Kode']})" if r["Kode"] else r["Menu"]): r["_kunci"]
                            for _, r in adaperubahan.iterrows()
                        }
                        pilih_menu_cmp = st.selectbox(
                            "Lihat penyebab perubahan menu", list(label_menu_cmp), key="cmp_detail"
                        )
                        baris_pilih = df_cmp[df_cmp["_kunci"] == label_menu_cmp[pilih_menu_cmp]].iloc[0]
                        st.markdown(
                            f"HPP **{rp(baris_pilih['HPP lama'])}** menjadi **{rp(baris_pilih['HPP baru'])}**. "
                            f"Efek harga bahan **{rp(baris_pilih['Efek harga'])}**, "
                            f"efek komposisi **{rp(baris_pilih['Efek komposisi'])}**."
                        )
                        det = rincian[label_menu_cmp[pilih_menu_cmp]]
                        st.dataframe(
                            det[det["Perubahan"] != "Tetap"],
                            hide_index=True,
                            column_config={
                                c: st.column_config.NumberColumn(c, format="%.2f")
                                for c in ["Qty lama", "Qty baru", "Harga lama", "Harga baru", "Dampak ke HPP (Rp)"]
                            },
                        )

                    info_excel = [
                        ("Snapshot lama", lama),
                        ("Snapshot baru", baru),
                        ("Sumber harga lama", sumber_map[id_lama]),
                        ("Sumber harga baru", sumber_map[id_baru]),
                        ("Menu naik", hitung.get("Naik", 0)),
                        ("Menu turun", hitung.get("Turun", 0)),
                        ("Menu tetap", hitung.get("Tetap", 0)),
                        ("Menu baru", hitung.get("Baru", 0)),
                        ("Menu dihapus", hitung.get("Dihapus", 0)),
                        ("Catatan", "Efek harga = dampak perubahan harga bahan. Efek komposisi = dampak bahan ditambah, dibuang, atau jumlah/yield berubah."),
                    ]
                    st.download_button(
                        "Unduh perbandingan (Excel)",
                        data=buat_excel(df_cmp, rincian, info_excel),
                        file_name=f"perbandingan_hpp_{lama[:7]}_vs_{baru[:7]}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )


st.divider()
if st.button("Keluar"):
    keluar()
