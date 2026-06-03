import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
from datetime import date

st.set_page_config(page_title="Cold Storage Integrator", layout="wide")

st.title("⚡ Cold Storage Integrator Dashboard")
st.write("Digital Twin Cold Storage Berdasarkan Database EnergyPlus & Batasan Termodinamika Komponen Bitzer")

# ==================== KUMPULAN INPUT SIDEBAR ====================
st.sidebar.header("📅 Pengaturan Waktu Operasional")

rentang_tanggal = st.sidebar.date_input(
    "Pilih Periode Penyimpanan",
    value=(date(2026, 3, 1), date(2026, 3, 7)), 
    min_value=date(2026, 1, 1),
    max_value=date(2026, 12, 31),
    key="kalender_traveloka"
)

st.sidebar.header("🏢 Pilih Ruang yang Aktif")
abf_on = st.sidebar.checkbox("Air Blast Freezer (ABF)", value=True, key='chk_abf')
anteroom_on = st.sidebar.checkbox("Anteroom (Ruang Perantara)", value=True, key='chk_ante')
f1_on = st.sidebar.checkbox("Freezer 1", value=True, key='chk_f1')
f2_on = st.sidebar.checkbox("Freezer 2", value=False, key='chk_f2')
f3_on = st.sidebar.checkbox("Freezer 3", value=False, key='chk_f3')
f4_on = st.sidebar.checkbox("Freezer 4", value=False, key='chk_f4')

st.sidebar.header("🐟 Parameter Produk Ikan")
tonase = st.sidebar.number_input("Total Muatan Ikan (Ton)", min_value=0.1, max_value=100.0, value=5.0, key='input_tonase')

# Proses translasi tanggal kalender ke indeks baris EnergyPlus (1 hari = 24 jam)
if isinstance(rentang_tanggal, tuple) and len(rentang_tanggal) == 2:
    tgl_mulai, tgl_selesai = rentang_tanggal
    hari_mulai = (tgl_mulai - date(2026, 1, 1)).days + 1
    durasi_hari = (tgl_selesai - tgl_mulai).days
    if durasi_hari == 0: durasi_hari = 1 
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
        st.error("File 'NoLoad.csv' gak ketemu Mek! Taruh filenya sejajar sama script python ini ya.")
        st.stop()
        
    start_row = (hari_mulai - 1) * 24
    end_row = start_row + (durasi_hari * 24)
    total_jam = durasi_hari * 24
    
    df_skenario = df.iloc[start_row:end_row].copy()
    
    # ---- 3. HITUNG BEBAN BANGUNAN BERDASARKAN JADWAL OPERASIONAL (JAM 7-17) ----
    df_skenario['Jam_Aktual'] = df_skenario['Date/Time'].str.split().str[1].str.split(':').str[0].astype(int)
    q_bangunan_total_kw = np.zeros(total_jam)
    jam_array = df_skenario['Jam_Aktual'].values
    
    # Mengatasi variasi penulisan spasi gaib pada nama kolom CSV
    df_skenario.columns = df_skenario.columns.str.strip()
    
    def ambil_data_zone(kolom_nama):
        if kolom_nama in df_skenario.columns:
            return df_skenario[kolom_nama].values
        else:
            return np.zeros(total_jam)
            
    if abf_on:
        abf_joule = ambil_data_zone('ABF IDEAL LOADS AIR SYSTEM:Zone Ideal Loads Zone Total Cooling Energy [J](Hourly)')
        q_bangunan_total_kw += np.where((jam_array >= 7) & (jam_array <= 17), abf_joule / 3.6e6, 0.0)
        
    if anteroom_on:
        ante_joule = ambil_data_zone('ANTEROOM IDEAL LOADS AIR SYSTEM:Zone Ideal Loads Zone Total Cooling Energy [J](Hourly)')
        q_bangunan_total_kw += np.where((jam_array >= 7) & (jam_array <= 17), ante_joule / 3.6e6, 0.0)
        
    if f1_on: q_bangunan_total_kw += ambil_data_zone('FREEZER1 IDEAL LOADS AIR SYSTEM:Zone Ideal Loads Zone Total Cooling Energy [J](Hourly)') / 3.6e6
    if f2_on: q_bangunan_total_kw += ambil_data_zone('FREEZER2 IDEAL LOADS AIR SYSTEM:Zone Ideal Loads Zone Total Cooling Energy [J](Hourly)') / 3.6e6
    if f3_on: q_bangunan_total_kw += ambil_data_zone('FREEZER3 IDEAL LOADS AIR SYSTEM:Zone Ideal Loads Zone Total Cooling Energy [J](Hourly)') / 3.6e6
    if f4_on: q_bangunan_total_kw += ambil_data_zone('FREEZER4 IDEAL LOADS AIR SYSTEM:Zone Ideal Loads Zone Total Cooling Energy [J](Hourly)') / 3.6e6

    df_skenario['Q_Bangunan_Gedung_kW'] = q_bangunan_total_kw

    # ---- 4. HITUNG OTOMATIS DURASI PEMBEBUAN RIIL (ASHRAE + BITZER PERFORMANCE) ----
    # ---- 4. HITUNG OTOMATIS DURASI PEMBEBUAN RIIL (ASHRAE + BITZER PERTAMA MASUK JAM 7 PAGI) ----
    m_kg = tonase * 1000 
    cp_above = 3.63   # kJ/kg C
    cp_below = 1.97   # kJ/kg C
    h_latent = 255.0  # kJ/kg
    t_freeze = -2.2   # Titik awal beku ikan (C)
    t_in = 4.0        # Suhu awal produk masuk (4 C)
    t_out = -18.0     # Suhu target penyimpanan beku (C)
    
    # Hitung total energi pembekuan fisis (kJ)
    total_energi_pembekuan_kj_per_kg = (cp_above * (t_in - t_freeze)) + h_latent + (cp_below * (t_freeze - t_out))
    total_kalor_produk_kj = m_kg * total_energi_pembekuan_kj_per_kg
    
    # Spek Riil Kompresor Booster Lu dari Bitzer Software [cite: 233, 239]
    KAPASITAS_MAKS_BOOSTER = 65.3   # Bitzer HSN8571 (kW) [cite: 239, 263]
    DAYA_KOMPRESI_BOOSTER = 38.4    # Pe Bitzer HSN8571 (kW) [cite: 264]
    
    # Menghitung durasi jam riil pembekuan murni berbasis kapasitas mesin
    waktu_beku_riil_jam = total_kalor_produk_kj / (KAPASITAS_MAKS_BOOSTER * 3600)
    waktu_beku_pembulatan = int(np.ceil(waktu_beku_riil_jam)) # Dibulatkan ke atas ke jam terdekat
    
    q_holding_kw = tonase * 0.01 
    q_ikan_per_jam = []
    status_fase_ikan = [] 
    
    # Indeks penanda kapan mesin mulai start nyala pertama kali
    jam_mulai_blasting = -1
    
    for jam in range(total_jam):
        jam_ke_berapa_hari_ini = jam_array[jam]
        
        # LOGIKA SAKLAR: Cari tahu kapan jam 7 pagi di hari pertama simulasi muncul
        if jam < 24 and jam_ke_berapa_hari_ini == 7 and jam_mulai_blasting == -1:
            jam_mulai_blasting = jam
            
        # Jalankan fase BLASTING selama durasi 'waktu_beku_pembulatan' dihitung sejak jam 7 pagi hari pertama
        if (jam_mulai_blasting != -1) and (jam < jam_mulai_blasting + waktu_beku_pembulatan):
            q_ikan_per_jam.append(KAPASITAS_MAKS_BOOSTER)
            status_fase_ikan.append("BLASTING")
        else:
            q_ikan_per_jam.append(q_holding_kw)
            status_fase_ikan.append("HOLDING")
            
    df_skenario['Q_Ikan_Produk_kW'] = q_ikan_per_jam
    df_skenario['Fase_Produk'] = status_fase_ikan
    
    # ---- 5. INTEGRASI LIMITASI PERFORMA KOMPRESOR HIGH-STAGE BITZER ----
    df_skenario['Total_Load_Ideal_kW'] = df_skenario['Q_Bangunan_Gedung_kW'] + df_skenario['Q_Ikan_Produk_kW']
    
    KAPASITAS_MAKS_PER_HS = 190.0   # 1 unit High-Stage Bitzer HSK9573 (kW)
    TOTAL_KAPASITAS_HS = 380.0      # 2 unit High-Stage Paralel (kW)
    
    df_skenario['Total_Load_Aktual_Mesin_kW'] = np.minimum(df_skenario['Total_Load_Ideal_kW'], TOTAL_KAPASITAS_HS)
    
    # Export CSV siap feed untuk sirkuit HYSYS
    df_skenario[['Date/Time', 'Total_Load_Aktual_Mesin_kW']].to_csv("input_beban_hysys.csv", index=False)
    
    # ==================== PANEL DISPLAY WEB STREAMLIT ====================
    st.success(f"Skenario Berhasil Dihitung dari {tgl_mulai} sampai {tgl_selesai} ({total_jam} Jam Operasional)!")
    
    # Tampilkan rekomendasi waktu beku hasil hitungan termodinamika riil
    st.info(f"💡 **HASIL ANALISIS:** Berdasarkan kalkulasi properti ASHRAE, pembekuan {tonase} Ton ikan tuna dari suhu {t_in}°C menuju {t_out}°C membutuhkan waktu pembekuan intensif murni selama **{round(waktu_beku_riil_jam, 2)} Jam**.")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Beban Puncak Ideal (Demand)", f"{round(df_skenario['Total_Load_Ideal_kW'].max(), 2)} kW")
    col2.metric("Limitasi Alat (2x High-Stage)", f"{TOTAL_KAPASITAS_HS} kW")
    col3.metric("Beban Maksimal Aktual Mesin", f"{round(df_skenario['Total_Load_Aktual_Mesin_kW'].max(), 2)} kW")
    
    fig = px.line(
        df_skenario, 
        x='Date/Time', 
        y=['Total_Load_Ideal_kW', 'Total_Load_Aktual_Mesin_kW', 'Q_Bangunan_Gedung_kW'],
        labels={'value': 'Beban Termal (kW)', 'Date/Time': 'Waktu'},
        title="Profil Beban Evaporator: Tuntutan Ideal ASHRAE vs Kemampuan Riil Komponen Bitzer"
    )
    st.plotly_chart(fig, use_container_width=True, key="grafik_beban_utama")

    # ==================== LOGIKA MONITORING SAKLAR KOMPRESOR & VFD REVISI INTEGRASI ====================
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
        
        # A. Status Booster ABF (Bitzer HSN8571)
        if abf_on and (fase_ini == "BLASTING"):
            status_booster.append("ON (100% - Lembur)")
            # Sesuai hukum sirkuit dual-stage, jika booster nyala, High-Stage memikul tambahan daya listrik kompresor booster
            load_high_stage_aktual = load_jam_ini + DAYA_KOMPRESI_BOOSTER 
        else:
            status_booster.append("OFF (0%)")
            load_high_stage_aktual = load_jam_ini

        # B. Status Dual High-Stage Compressor Paralel + VFD Logic (Lead-Lag Execution)
        if load_high_stage_aktual <= 0.1:
            status_hs1.append("OFF")
            status_hs2.append("OFF")
            vfd_hs1.append(0.0)
            vfd_hs2.append(0.0)
            
        elif load_high_stage_aktual <= KAPASITAS_MAKS_PER_HS:  
            status_hs1.append("ON (Lead - VFD Mode)")
            status_hs2.append("OFF (Lag - Standby)")
            pct = (load_high_stage_aktual / KAPASITAS_MAKS_PER_HS) * 100
            vfd_hs1.append(round(max(pct, 30.0), 1))  
            vfd_hs2.append(0.0)
            
        else:  
            status_hs1.append("ON (Lead - 100%)")
            status_hs2.append("ON (Lag - VFD Bantuin)")
            vfd_hs1.append(100.0)
            sisa_load = load_high_stage_aktual - KAPASITAS_MAKS_PER_HS
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
