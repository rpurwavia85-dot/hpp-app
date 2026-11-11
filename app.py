import html
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
    try:
        data = db.table(tabel).select("*").execute().data
    except Exception as e:
        if "jwt" in str(e).lower() or "expired" in str(e).lower():
            keluar("Sesi sudah habis, silakan masuk lagi.")
        raise
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
    ["id", "nama_bahan", "satuan", "stok_saat_ini", "stok_minimum"],
    ["id", "stok_saat_ini", "stok_minimum"],
)
pembelian = ambil(
    "pembelian",
    ["id", "tanggal", "id_bahan", "jumlah", "total_harga", "supplier"],
    ["id", "id_bahan", "jumlah", "total_harga"],
)
menu = ambil(
    "menu",
    ["id", "nama_menu", "harga_jual", "jumlah_porsi_per_resep"],
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

tab1, tab2, tab3 = st.tabs(["📦 Bahan & Pembelian", "📖 Menu & Resep", "📊 Laporan"])

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
        "HPP dihitung dari harga rata-rata seluruh pembelian. "
        f"Kartu merah = margin di bawah {BATAS_MARGIN}%. Urutan dari margin (%) terkecil."
    )

    if menu.empty:
        st.info("Belum ada menu. Tambahkan dulu di halaman Menu & Resep.")
    else:
        # harga rata-rata per satuan bahan = total uang / total jumlah dibeli
        harga_satuan = {}
        if not pembelian.empty:
            ringkas = pembelian.groupby("id_bahan")[["total_harga", "jumlah"]].sum()
            harga_satuan = (ringkas["total_harga"] / ringkas["jumlah"]).to_dict()

        hasil = []
        for m in menu.itertuples():
            baris_resep = resep[resep["id_menu"] == m.id]
            biaya = 0.0
            ada_bahan_tanpa_harga = False
            for b in baris_resep.itertuples():
                h = harga_satuan.get(b.id_bahan)
                if h is None:
                    ada_bahan_tanpa_harga = True
                else:
                    biaya += b.jumlah_dipakai * h

            hpp = biaya / m.jumlah_porsi_per_resep
            margin_rp = m.harga_jual - hpp
            margin_pct = (margin_rp / m.harga_jual * 100) if m.harga_jual > 0 else 0

            catatan = ""
            if baris_resep.empty:
                catatan = "Resep belum diisi."
            elif ada_bahan_tanpa_harga:
                catatan = "Ada bahan yang belum pernah dicatat pembeliannya, HPP bisa terlalu kecil."

            hasil.append((m.nama_menu, m.harga_jual, hpp, margin_rp, margin_pct, catatan))

        hasil.sort(key=lambda x: x[4])  # margin % terkecil di atas

        jumlah_merah = sum(1 for x in hasil if x[4] < BATAS_MARGIN)
        st.metric("Menu dengan margin rendah", f"{jumlah_merah} dari {len(hasil)}")

        for nama_m, hj, hpp, mrp, mpct, catatan in hasil:
            merah = mpct < BATAS_MARGIN
            warna_bg = "#fdecea" if merah else "#eef7ee"
            warna_garis = "#d93025" if merah else "#2e7d32"
            teks_catatan = (
                f"<br><span style='font-size:0.85rem'>ℹ️ {html.escape(catatan)}</span>"
                if catatan
                else ""
            )
            kartu = (
                f"<div style='background:{warna_bg};border-left:6px solid {warna_garis};"
                f"padding:12px 14px;border-radius:10px;margin-bottom:10px;color:#222'>"
                f"<b style='font-size:1.05rem'>{html.escape(nama_m)}</b><br>"
                f"Harga jual: {rp(hj)}<br>"
                f"HPP per porsi: {rp(hpp)}<br>"
                f"Margin: <b>{rp(mrp)} ({mpct:.1f}%)</b>"
                f"{teks_catatan}</div>"
            )
            st.markdown(kartu, unsafe_allow_html=True)

st.divider()
if st.button("Keluar"):
    keluar()
