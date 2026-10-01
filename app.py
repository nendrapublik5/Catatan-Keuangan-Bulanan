import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import json
import google.generativeai as genai
from PIL import Image

# ----------------- KONFIGURASI HALAMAN -----------------
st.set_page_config(page_title="Personal Finance & Salary Tracker", page_icon="💴", layout="wide")

# Inisialisasi Database SQLite
conn = sqlite3.connect("finance_tracker.db", check_same_thread=False)
cursor = conn.cursor()

# Tabel Transaksi Pengeluaran
cursor.execute('''
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        month_period TEXT,
        store TEXT,
        category TEXT,
        item_name TEXT,
        qty REAL,
        unit TEXT,
        unit_price REAL,
        total_price REAL,
        payment_method TEXT,
        notes TEXT
    )
''')

# Tabel Keuangan Bulanan (Gaji & Batas Anggaran)
cursor.execute('''
    CREATE TABLE IF NOT EXISTS monthly_financials (
        month_period TEXT PRIMARY KEY,
        salary REAL DEFAULT 0,
        budget_limit REAL DEFAULT 0
    )
''')
conn.commit()

# Master Kategori & Metode Pembayaran Baku
CATEGORIES = [
    "Beras & Makanan Pokok", "Sayur & Buah", "Daging, Ayam & Ikan", 
    "Bahan Makanan & Minuman", "Bumbu & Dapur", "Elektronik & Gadget", 
    "Peralatan Rumah Tangga", "Perlengkapan & Kebersihan", "Pakaian & Perlengkapan", 
    "Alat Tulis & Kantor", "Camilan & Minuman Santai", "Tagihan & Utilitas", "Lain-lain"
]
PAYMENT_METHODS = ["Tunai / Cash", "Kartu Debit/Kredit", "QRIS / E-Wallet", "Transfer Bank", "PayPay"]

# ----------------- SIDEBAR PENGATURAN & ARSIP -----------------
st.sidebar.title("⚙️ Keuangan & Periode")
current_month_str = datetime.now().strftime("%Y-%m")

# Ambil histori bulan yang ada di database
months_df = pd.read_sql_query("SELECT DISTINCT strftime('%Y-%m', date) as m FROM transactions ORDER BY m DESC", conn)
available_months = months_df['m'].tolist() if not months_df.empty else [current_month_str]
if current_month_str not in available_months:
    available_months.insert(0, current_month_str)

selected_month = st.sidebar.selectbox("📅 Pilih Arsip Bulan:", available_months)

# Ambil data Gaji & Target Anggaran untuk bulan terpilih
fin_data = cursor.execute("SELECT salary, budget_limit FROM monthly_financials WHERE month_period = ?", (selected_month,)).fetchone()
saved_salary = fin_data[0] if fin_data else 0.0
saved_budget = fin_data[1] if fin_data else 60000.0

st.sidebar.markdown("---")
st.sidebar.subheader("💵 Pengaturan Pemasukan & Target")
input_salary = st.sidebar.number_input("Gaji Masuk / Pemasukan (¥):", min_value=0.0, value=float(saved_salary), step=10000.0)
input_budget = st.sidebar.number_input("Plafon Maksimal Belanja (¥):", min_value=1000.0, value=float(saved_budget), step=5000.0)

if st.sidebar.button("💾 Simpan Data Pemasukan & Target"):
    cursor.execute('''
        INSERT OR REPLACE INTO monthly_financials (month_period, salary, budget_limit)
        VALUES (?, ?, ?)
    ''', (selected_month, input_salary, input_budget))
    conn.commit()
    st.sidebar.success("Gaji dan target anggaran berhasil diperbarui!")
    st.rerun()

st.sidebar.markdown("---")
gemini_api_key = st.sidebar.text_input("🔑 Gemini API Key (Scan Foto):", type="password")
if gemini_api_key:
    genai.configure(api_key=gemini_api_key)

# ----------------- PERHITUNGAN BIAYA & SISA GAJI -----------------
st.title(f"💴 Financial Dashboard: {selected_month}")

df_month = pd.read_sql_query("SELECT * FROM transactions WHERE strftime('%Y-%m', date) = ?", conn, params=(selected_month,))
total_spent = df_month['total_price'].sum() if not df_month.empty else 0.0
remaining_salary = input_salary - total_spent
pct_budget = (total_spent / input_budget * 100) if input_budget > 0 else 0
pct_salary_used = (total_spent / input_salary * 100) if input_salary > 0 else 0

# Tampilan Kartu Metrik Keuangan
col_m1, col_m2, col_m3, col_m4 = st.columns(4)
col_m1.metric("💵 Gaji Masuk", f"¥{input_salary:,.0f}")
col_m2.metric("🛒 Total Pengeluaran", f"¥{total_spent:,.0f}")
col_m3.metric(
    "💰 Sisa Gaji Terbaru", 
    f"¥{remaining_salary:,.0f}", 
    delta=f"{100 - pct_salary_used:.1f}% sisa dana" if input_salary > 0 else None,
    delta_color="normal" if remaining_salary >= 0 else "inverse"
)
col_m4.metric("🎯 Plafon Belanja", f"¥{input_budget:,.0f}", f"{pct_budget:.1f}% terpakai", delta_color="inverse")

# Indikator Peringatan (Warning System)
if input_salary > 0 and remaining_salary < 0:
    st.error(f"🚨 **DEFISIT KRITIS**: Pengeluaran telah melampaui total gaji masuk sebesar ¥{abs(remaining_salary):,.0f}!")
elif pct_budget >= 100:
    st.error(f"🚨 **ANGGARAN JEBOL**: Pengeluaran melampaui plafon target belanja sebesar ¥{total_spent - input_budget:,.0f}!")
elif pct_budget >= 80:
    st.warning(f"⚠️ **PERINGATAN AWAS**: Belanja bulanan telah mencapai {pct_budget:.1f}% dari batas target (Sisa anggaran belanja: ¥{max(input_budget - total_spent, 0.0):,.0f}).")
else:
    st.success(f"✅ **KONDISI AMAN**: Pengeluaran terkontrol rapi. Anda masih memiliki sisa gaji sebesar ¥{remaining_salary:,.0f}.")

st.write(f"Rasio Pemakaian Gaji ({pct_salary_used:.1f}% terpakai):")
st.progress(min(pct_salary_used / 100, 1.0) if input_salary > 0 else 0.0)

# ----------------- TABS INTERAKSI -----------------
tab_scan, tab_manual, tab_data = st.tabs(["📸 Scan Foto Struk", "✍️ Input Pengeluaran Manual", "📋 Histori & Grafik"])

with tab_scan:
    st.subheader("Pindai Struk dengan AI")
    uploaded_file = st.file_uploader("Unggah Foto Struk (JPG/PNG)", type=["jpg", "png", "jpeg"])
    
    if uploaded_file and gemini_api_key:
        image = Image.open(uploaded_file)
        st.image(image, caption="Foto Struk Masuk", width=280)
        
        if st.button("Jalankan Ekstraksi AI"):
            with st.spinner("Membaca struk dan menghitung rincian harga..."):
                model = genai.GenerativeModel('gemini-1.5-flash')
                prompt = f"""
                Kamu adalah asisten keuangan di Jepang. Analisis struk belanja ini dan keluarkan HANYA array JSON murni tanpa format markdown:
                [
                  {{
                    "date": "YYYY-MM-DD",
                    "store": "Nama Toko / Tempat Belanja",
                    "category": "Pilih satu: {json.dumps(CATEGORIES)}",
                    "item_name": "Nama item (Jepang & arti Indonesia)",
                    "qty": 1,
                    "unit": "pcs/pack/kg/botol/unit/bulan",
                    "unit_price": 100,
                    "total_price": 100,
                    "payment_method": "Pilih: Tunai / Cash / PayPay / Kartu Debit/Kredit",
                    "notes": "keterangan promo/pajak"
                  }}
                ]
                Pastikan total_price adalah harga final netto setelah diskon dan pajak.
                """
                response = model.generate_content([prompt, image])
                clean_json = response.text.replace("```json", "").replace("```", "").strip()
                try:
                    parsed_data = json.loads(clean_json)
                    st.session_state['temp_ocr_items'] = parsed_data
                    st.success(f"Terbaca {len(parsed_data)} item transaksi!")
                except Exception:
                    st.error("Format data struk belum terbaca sempurna. Silakan periksa pencahayaan foto.")

    if 'temp_ocr_items' in st.session_state:
        st.write("Verifikasi & Koreksi Data Sebelum Simpan:")
        edited_df = st.data_editor(pd.DataFrame(st.session_state['temp_ocr_items']), num_rows="dynamic")
        if st.button("Konfirmasi & Simpan ke Database"):
            for _, row in edited_df.iterrows():
                cursor.execute('''
                    INSERT INTO transactions (date, month_period, store, category, item_name, qty, unit, unit_price, total_price, payment_method, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (row['date'], selected_month, row['store'], row['category'], row['item_name'], row['qty'], row['unit'], row['unit_price'], row['total_price'], row['payment_method'], row['notes']))
            conn.commit()
            st.success("Transaksi berhasil masuk buku kas!")
            del st.session_state['temp_ocr_items']
            st.rerun()

with tab_manual:
    st.subheader("Catat Pengeluaran Tanpa Struk")
    with st.form("manual_tx_form"):
        f_col1, f_col2, f_col3 = st.columns(3)
        m_date = f_col1.date_input("Tanggal", datetime.now())
        m_store = f_col2.text_input("Toko / Layanan", "Yaoko (ヤオコー)")
        m_cat = f_col3.selectbox("Kategori", CATEGORIES)
        
        m_item = f_col1.text_input("Nama Barang / Tagihan")
        m_qty = f_col2.number_input("Qty", min_value=1.0, value=1.0, step=1.0)
        m_unit = f_col3.selectbox("Satuan", ["pcs", "pack", "kg", "gram", "botol", "unit", "ikat", "set", "bulan"])
        
        m_price = f_col1.number_input("Harga Satuan (¥)", min_value=0.0, step=10.0)
        m_pay = f_col2.selectbox("Metode Pembayaran", PAYMENT_METHODS)
        m_notes = f_col3.text_input("Keterangan Tambahan")
        
        if st.form_submit_button("Simpan Transaksi Manual"):
            subtot = m_qty * m_price
            cursor.execute('''
                INSERT INTO transactions (date, month_period, store, category, item_name, qty, unit, unit_price, total_price, payment_method, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (str(m_date), selected_month, m_store, m_cat, m_item, m_qty, m_unit, m_price, subtot, m_pay, m_notes))
            conn.commit()
            st.success(f"Tersimpan: {m_item} (¥{subtot:,.0f})")
            st.rerun()

with tab_data:
    st.subheader(f"Arsip Transaksi Bulan {selected_month}")
    if not df_month.empty:
        # Grafik Distribusi
        g_col1, g_col2 = st.columns(2)
        cat_agg = df_month.groupby("category")["total_price"].sum().reset_index()
        g_col1.write("Pengeluaran per Kategori:")
        g_col1.bar_chart(cat_agg, x="category", y="total_price")
        
        store_agg = df_month.groupby("store")["total_price"].sum().reset_index()
        g_col2.write("Pengeluaran per Merchant / Toko:")
        g_col2.bar_chart(store_agg, x="store", y="total_price")
        
        # Tabel Detail
        st.dataframe(
            df_month[["id", "date", "store", "category", "item_name", "qty", "unit", "unit_price", "total_price", "payment_method", "notes"]],
            use_container_width=True
        )
        
        # Ekspor CSV
        csv_bytes = df_month.drop(columns=["id", "month_period"]).to_csv(index=False).encode('utf-8')
        st.download_button(
            "📥 Unduh Laporan (.csv)",
            data=csv_bytes,
            file_name=f"Laporan_Pengeluaran_{selected_month}.csv",
            mime="text/csv"
        )
    else:
        st.info("Belum ada pengeluaran yang tercatat pada bulan ini.")
