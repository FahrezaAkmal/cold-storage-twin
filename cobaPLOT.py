import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
from datetime import date

st.set_page_config(page_title="Cold Storage Integrator", layout="wide")

st.title("⚡ Cold Storage Integrator Dashboard")
st.write("Digital Twin Cold Storage Berdasarkan Database EnergyPlus & Batasan Termodinamika Komponen Bitzer")

# ==================== KUMPULAN INPUT SIDEBAR ====================
st.sidebar.header("📅 Periode Operasional Pendinginan")

# Widget Kalender Rentang Tanggal (User memilih tanggal mulai dan selesai dari kalender)
hari_ini = date(2026, 6, 3) # Basis tahun simulasi 2026
rentang_tanggal = st.sidebar.date_input(
    "Pilih Periode Penyimpanan",
    value=(date(2026, 3, 1), date(2026, 3, 7)), # Default seminggu di bulan Maret
    min_value=date(2026, 1, 1),
    max_value=date(2026, 12, 31),
    key="kalender_traveloka"
)

st.sidebar.header("🏢 Pilih Ruang Pendingin yang Aktif")
abf_on = st.sidebar.checkbox("Air Blast Freezer (ABF)", value=True, key='chk_abf')
anteroom_on = st.sidebar.checkbox("Anteroom (Ruang Perantara)", value=True, key='chk_ante')
f1_on = st.sidebar.checkbox("Freezer 1", value=True, key='chk_f1')
f2_on = st.sidebar.checkbox("Freezer 2", value=False, key='chk_f2')
f3_on = st.sidebar.checkbox("Freezer 3", value=False, key='chk_f3')
f4_on = st.sidebar.checkbox("Freezer 4", value=False, key='chk_f4')

st.sidebar.header("🐟 Parameter Produk Ikan")
tonase = st.sidebar.number_input("Total Muatan Ikan (Ton)", min_value=0.1, max_value=100.0, value=5.0, key='input_tonase')
waktu_beku = st.sidebar.slider("Target Waktu Pembekuan Intensif (Jam)", min_value=6, max_value=48, value=24, key='slider_waktu_beku')

# Proses translasi tanggal kalender ke indeks baris EnergyPlus (1 hari = 24 jam)
if isinstance(rentang_tanggal, tuple) and len(rentang_tanggal) == 2:
    tgl_mulai, tgl_selesai = rentang_tanggal
    
    # Hitung hari ke-berapa dari 1 Januari
    hari_mulai = (tgl_mulai - date(2026, 1, 1)).days + 1
    durasi_hari = (tgl_selesai - tgl_mulai).days
    if durasi_hari == 0: durasi_hari = 1 # Minimal 1 hari pencegahan eror
else:
    hari_mulai = 60
    durasi_hari = 7

# ==================== UTAMA: PROSES DATA SCRIPT ====================
if st.button("📊 Jalankan Skenario & Hitung Total Load"):
    
    # ---- 1. VALIDASI KAPASITAS FISIK RUANGAN ----
    kapasitas_maks_total = 0
    if abf_on: kapasitas_maks_total += 10.0  
    if f1_on: kapasitas_maks_total += 25.0
    if f2_on: kapasitas_maks_total += 25.0
    if f3_on: kapasitas_maks_total += 25.0
    if f4_on: kapasitas_maks_total += 25.0

    if tonase > kapasitas_maks_total:
        st.error(f"🚨 OVERLOAD GEOMETRI: Total muatan ({tonase} Ton) melebihi kapasitas fisik ruangan aktif yang cuma {kapasitas_maks_total} Ton.")
        st.stop()
    
    # ---- 2. BACA DATABASE ENERGYPLUS ----
    try:
        df = pd.read_csv("NoLoad.csv")
    except FileNotFoundError:
        st.error("File 'NoLoad.csv' gak ketemu! Taruh filenya sejajar sama script python ini ya.")
        st.stop()
        
    start_row = (hari_mulai - 1) * 24
    end_row = start_row + (durasi_hari * 24)
    total_jam = durasi_hari * 24
    
    df_skenario = df.iloc[start_row:end_row].copy()
    
    # ---- 3. HITUNG BEBAN BANGUNAN BERDASARKAN JADWAL OPERASIONAL (JAM 7-17) ----
    # ---- 3. HITUNG BEBAN BANGUNAN BERDASARKAN JADWAL OPERASIONAL (JAM 7-17) ----
    df_skenario['Jam_Aktual'] = df_skenario['Date/Time'].str.split().str[1].str.split(':').str[0].astype(int)
    q_bangunan_total_kw = np.zeros(total_jam)
    jam_array = df_skenario['Jam_Aktual'].values
    
    # Fungsi bantu untuk ngecek kolom ada atau enggak di CSV lu, biar gak KeyError
    def ambil_data_zone(kolom_nama):
        if kolom_nama in df_skenario.columns:
            return df_skenario[kolom_nama].values
        else:
            # Cari nama kolom yang mirip-mirip di CSV lu buat ngasih petunjuk
            kata_kunci = kolom_nama.split()[0] # misal 'FREEZER4' atau 'ABF'
            kolom_mirip = [c for c in df_skenario.columns if kata_kunci in c]
            st.warning(f"⚠️ Kolom '{kolom_nama}' gak ketemu di CSV lu! Apakah maksudnya: {kolom_mirip}?")
            return np.zeros(total_jam) # Kasih nilai 0 aja biar gak crash eror merah
            
    if abf_on:
        abf_joule = ambil_data_zone('ABF IDEAL LOADS AIR SYSTEM:Zone Ideal Loads Zone Total Cooling Energy [J](Hourly)')
        q_bangunan_total_kw += np.where((jam_array >= 7) & (jam_array <= 17), abf_joule / 3.6e6, 0.0)
        
    if anteroom_on:
        ante_joule = ambil_data_zone('ANTEROOM IDEAL LOADS AIR SYSTEM:Zone Ideal Loads Zone Total Cooling Energy [J](Hourly)')
        q_bangunan_total_kw += np.where((jam_array >= 7) & (jam_array <= 17), ante_joule / 3.6e6, 0.0)
        
    if f1_on: 
        q_bangunan_total_kw += ambil_data_zone('FREEZER1 IDEAL LOADS AIR SYSTEM:Zone Ideal Loads Zone Total Cooling Energy [J](Hourly)') / 3.6e6
    if f2_on: 
        q_bangunan_total_kw += ambil_data_zone('FREEZER2 IDEAL LOADS AIR SYSTEM:Zone Ideal Loads Zone Total Cooling Energy [J](Hourly)') / 3.6e6
    if f3_on: 
        q_bangunan_total_kw += ambil_data_zone('FREEZER3 IDEAL LOADS AIR SYSTEM:Zone Ideal Loads Zone Total Cooling Energy [J](Hourly)') / 3.6e6
    if f4_on: 
        # Tambahkan spasi di ujung setelah huruf J sebelum tanda petik tutup
        q_bangunan_total_kw += ambil_data_zone('FREEZER4 IDEAL LOADS AIR SYSTEM:Zone Ideal Loads Zone Total Cooling Energy [J](Hourly) ') / 3.6e6

    df_skenario['Q_Bangunan_Gedung_kW'] = q_bangunan_total_kw

    # ---- 4. HITUNG BEBAN IKAN BERDASARKAN PERSAMAAN TERMODINAMIKA ASHRAE ----
    # Konversi tonase ke kg murni untuk hukum termodinamika
    m_kg = tonase * 1000 
    
    # Konstanta fisis properti ikan standar ASHRAE
    cp_above = 3.63  # kJ/kg C
    cp_below = 1.97  # kJ/kg C
    h_latent = 255.0 # kJ/kg
    t_freeze = -2.2  # Titik awal beku ikan (C) 
    
    # Asumsi kondisi temperatur operasional
    t_in = 25.0      # Suhu ikan segar masuk (suhu ruang)
    t_out = -18.0     # Suhu target akhir holding room
    
    # Hitung total energi pembekuan komponen kalor (kJ/kg)
    q_sensible_above = cp_above * (t_in - t_freeze)
    q_sensible_below = cp_below * (t_freeze - t_out)
    total_energi_pembekuan_kj_per_kg = q_sensible_above + h_latent + q_sensible_below
    
    # Total energi untuk keseluruhan massa ikan (kJ)
    total_kalor_produk_kj = m_kg * total_energi_pembekuan_kj_per_kg
    
    # Hitung daya evaporator beban puncak intensif (kW = kJ / sekon)
    # total detik = waktu_beku (jam) * 3600 detik
    q_blasting_kw = total_kalor_produk_kj / (waktu_beku * 3600)
    q_holding_kw = tonase * 0.01 # Beban maintenance sangat kecil saat ikan sudah jadi es batu
    
    q_ikan_per_jam = []
    status_fase_ikan = [] 
    
    for jam in range(total_jam):
        if jam < waktu_beku:
            q_ikan_per_jam.append(q_blasting_kw) # Fase Pembekuan Intensif di ABF (Nilai ASHRAE Akurat!)
            status_fase_ikan.append("BLASTING")
        else:
            q_ikan_per_jam.append(q_holding_kw)  # Fase Menjaga Suhu di Freezer
            status_fase_ikan.append("HOLDING")
            
    df_skenario['Q_Ikan_Produk_kW'] = q_ikan_per_jam
    df_skenario['Fase_Produk'] = status_fase_ikan
    
    # ---- 5. INTEGRASI LIMITASI PERFORMA KOMPRESOR BITZER RIIL ----
    df_skenario['Total_Load_Ideal_kW'] = df_skenario['Q_Bangunan_Gedung_kW'] + df_skenario['Q_Ikan_Produk_kW']
    
    KAPASITAS_MAKS_PER_HS = 190.0   # 1 unit High-Stage Bitzer HSK9573 (kW) [cite: 82, 233, 271, 293]
    TOTAL_KAPASITAS_HS = 380.0      # 2 unit High-Stage Paralel (kW)
    
    df_skenario['Total_Load_Aktual_Mesin_kW'] = np.minimum(df_skenario['Total_Load_Ideal_kW'], TOTAL_KAPASITAS_HS)
    
    if df_skenario['Total_Load_Ideal_kW'].max() > TOTAL_KAPASITAS_HS:
        st.warning(f"🚨 OVERLOAD COMPRESSOR: Beban puncak ({round(df_skenario['Total_Load_Ideal_kW'].max(), 2)} kW) melebihi batas maksimal 2 unit High Stage ({TOTAL_KAPASITAS_HS} kW)!")

    # Export CSV siap feed untuk sirkuit HYSYS
    df_skenario[['Date/Time', 'Total_Load_Aktual_Mesin_kW']].to_csv("input_beban_hysys.csv", index=False)
    
    # ==================== PANEL DISPLAY WEB STREAMLIT ====================
    st.success(f"Skenario Berhasil Dihitung dari {tgl_mulai} sampai {tgl_selesai} ({total_jam} Jam Operasional)!")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Beban Puncak Ideal (Demand)", f"{round(df_skenario['Total_Load_Ideal_kW'].max(), 2)} kW")
    col2.metric("Limitasi Alat (2x High-Stage)", f"{TOTAL_KAPASITAS_HS} kW")
    col3.metric("Beban Maksimal Aktual Mesin", f"{round(df_skenario['Total_Load_Aktual_Mesin_kW'].max(), 2)} kW")
    
    # Plot Grafik Utama
    fig = px.line(
        df_skenario, 
        x='Date/Time', 
        y=['Total_Load_Ideal_kW', 'Total_Load_Aktual_Mesin_kW', 'Q_Bangunan_Gedung_kW'],
        labels={'value': 'Beban Termal (kW)', 'Date/Time': 'Waktu'},
        title="Profil Beban Evaporator: Tuntutan Ideal ASHRAE vs Kemampuan Riil Komponen Bitzer"
    )
    st.plotly_chart(fig, use_container_width=True, key="grafik_beban_utama")

    # ==================== LOGIKA MONITORING SAKLAR KOMPRESOR & VFD ====================
    status_booster = []
    status_hs1 = []
    status_hs2 = []
    vfd_hs1 = []
    vfd_hs2 = []

    beban_aktual_array = df_skenario['Total_Load_Aktual_Mesin_kW'].values
    fase_ikan_array = df_skenario['Fase_Produk'].values

    for i in range(total_jam):
        load_jam_ini = beban_aktual_array[i]
        jam_ini = jam_array[i]
        fase_ini = fase_ikan_array[i]
        
        # A. Status Booster ABF (Bitzer HSN8571) [cite: 82, 233, 239, 266]
        if abf_on and (fase_ini == "BLASTING"):
            status_booster.append("ON (100% - Lembur)")
        else:
            status_booster.append("OFF (0%)")

        # B. Status Dual High-Stage Compressor Paralel + VFD Logic (Lead-Lag Execution)
        if load_jam_ini <= 0.1:
            status_hs1.append("OFF")
            status_hs2.append("OFF")
            vfd_hs1.append(0.0)
            vfd_hs2.append(0.0)
            
        elif load_jam_ini <= KAPASITAS_MAKS_PER_HS:  
            status_hs1.append("ON (Lead - VFD Mode)")
            status_hs2.append("OFF (Lag - Standby)")
            pct = (load_jam_ini / KAPASITAS_MAKS_PER_HS) * 100
            vfd_hs1.append(round(max(pct, 30.0), 1))  
            vfd_hs2.append(0.0)
            
        else:  
            status_hs1.append("ON (Lead - 100%)")
            status_hs2.append("ON (Lag - VFD Bantuin)")
            vfd_hs1.append(100.0)
            sisa_load = load_jam_ini - KAPASITAS_MAKS_PER_HS
            pct_comp2 = (sisa_load / KAPASITAS_MAKS_PER_HS) * 100
            vfd_hs2.append(round(max(pct_comp2, 30.0), 1))

    df_skenario['Status_Booster_ABF'] = status_booster
    df_skenario['VFD_HighStage_1_%'] = vfd_hs1
    df_skenario['VFD_HighStage_2_%'] = vfd_hs2

    st.markdown("---")
    st.subheader("🖥️ Real-time Compressor & VFD Status Monitoring Room (Bitzer Validated)")
    
    kolom_pantau = ['Date/Time', 'Total_Load_Aktual_Mesin_kW', 'Status_Booster_ABF', 'VFD_HighStage_1_%', 'VFD_HighStage_2_%']
    st.dataframe(df_skenario[kolom_pantau].rename(columns={
        'Total_Load_Aktual_Mesin_kW': 'Beban Evap (kW)',
        'Status_Booster_ABF': 'Booster ABF (HSN8571)',
        'VFD_HighStage_1_%': 'VFD HighStage 1 (Lead %)',
        'VFD_HighStage_2_%': 'VFD HighStage 2 (Lag %)'
    }), use_container_width=True)