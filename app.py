import html
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
def ambil(tabel, kolom, angka=()):
    """Ambil seluruh isi tabel sebagai DataFrame (tabel di memori)."""
    data = []
    mulai = 0
    while True:  # Supabase membatasi 1000 baris per permintaan, jadi ambil bertahap
        try:
            bagian = (
                db.table(tabel)
                .select("*")
                .order("id")
                .range(mulai, mulai + 999)
                .execute()
                .data
            )
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

tab1, tab2, tab3, tab4 = st.tabs(
    ["📦 Bahan & Pembelian", "📖 Menu & Resep", "📊 Laporan", "📥 Impor Excel"]
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


def siapkan(raw, peta, awal):
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
    raw = xls.parse(sheet, header=int(hdr) - 1, dtype=object)
    raw = raw.dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)
    raw.columns = [str(c).strip() for c in raw.columns]
    kolom = list(raw.columns)

    if raw.empty or not kolom:
        st.warning("Sheet ini kosong atau judul kolomnya tidak ditemukan. Coba ubah nomor baris judul.")
        return

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

    awal = int(hdr) + 1  # nomor baris Excel untuk data pertama
    menus, bahans, resep_rows, masalah, d = siapkan(raw, peta, awal)

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

st.divider()
if st.button("Keluar"):
    keluar()
