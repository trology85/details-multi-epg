import requests
import gzip
import xml.etree.ElementTree as ET
import io
import os
from datetime import datetime, timedelta
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- AYARLAR ---
SOURCES = {
    "DE": "https://epgshare01.online/epgshare01/epg_ripper_DE1.xml.gz",
    "FR": "https://epgshare01.online/epgshare01/epg_ripper_FR1.xml.gz",
    "GR": "https://epgshare01.online/epgshare01/epg_ripper_GR1.xml.gz"
}

WANTED_CHANNELS = {
    "RTL.de": "RTL", "ProSieben.de": "Pro7", "SAT.1.de": "SAT 1", "VOX.de": "Vox", "ZDF.de": "ZDF",
    "TF1.fr": "TF1", "M6.fr": "M6", "France2.fr": "France.2", "CanalPlus.fr": "Canal.Plus", "RTL.9.fr": "RTL 9",
    "ERT1.gr": "ERT1", "Mega.gr": "Mega", "Ant1.gr": "ANT1.gr", "Skai.gr": "Skai"
}

# --- YENI KAYNAK KANALLARI (Tivibu & Tivi6) ---
TIVIBU_CHANNELS = {
    "TivibuSpor1.tr": "TİVİBU SPOR 1",
    "TivibuSpor2.tr": "TİVİBU SPOR 2",
    "TivibuSpor3.tr": "TİVİBU SPOR 3",
    "TivibuSpor4.tr": "TİVİBU SPOR 4",
    "TIVI6.tr": "TİVİ6"
}

def fetch_turksat_weekly(master_root):
    tr_now = datetime.utcnow() + timedelta(hours=3)
    headers = {'User-Agent': 'Mozilla/5.0'}
    print("🇹🇷 Türksat Haftalık Tarama Başlatıldı...")
    
    for i in range(7):
        target_date = tr_now + timedelta(days=i)
        day_str = target_date.strftime("%d").lstrip('0')
        url = f"https://www.turksatkablo.com.tr/userUpload/EPG/{day_str}.json"
        
        try:
            r = requests.get(url, headers=headers, verify=False, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if 'k' in data:
                    print(f"✅ {target_date.strftime('%d.%m.%Y')} eklendi.")
                    for channel in data.get('k', []):
                        chan_name = channel.get('n', 'Unknown')
                        chan_id = chan_name.replace(" ", ".")
                        
                        if i == 0:
                            c_elem = ET.SubElement(master_root, "channel", id=chan_id)
                            ET.SubElement(c_elem, "display-name").text = chan_name

                        date_prefix = target_date.strftime('%Y%m%d')
                        for prog in channel.get('p', []):
                            start_time = prog.get('c', '').replace(":", "")
                            stop_time = prog.get('d', '').replace(":", "")
                            
                            # Gece yarısı devretme kontrolü (Stop Start'tan küçükse gün ekle)
                            current_stop_prefix = date_prefix
                            if int(stop_time) < int(start_time):
                                next_day = target_date + timedelta(days=1)
                                current_stop_prefix = next_day.strftime('%Y%m%d')

                            start = date_prefix + start_time + "00 +0300"
                            stop = current_stop_prefix + stop_time + "00 +0300"
                            
                            p_elem = ET.SubElement(master_root, "programme", start=start, stop=stop, channel=chan_id)
                            ET.SubElement(p_elem, "title", lang="tr").text = prog.get('b', 'Yayın Akışı')
        except Exception as e:
            print(f"⚠️ Türksat hatası ({target_date.strftime('%d.%m')}): {e}")

def fetch_tivibu_spor(master_root):
    url = "https://epgshare01.online/epgshare01/epg_ripper_TR3.xml.gz"
    print("📡 Tivibu Spor ve TİVİ6 Verileri Çekiliyor...")
    try:
        resp = requests.get(url, timeout=60)
        with gzip.GzipFile(fileobj=io.BytesIO(resp.content)) as f:
            context = ET.iterparse(f, events=("end",))
            for _, elem in context:
                if elem.tag == "channel":
                    orig_id = elem.get("id")
                    if orig_id in TIVIBU_CHANNELS:
                        elem.set("id", TIVIBU_CHANNELS[orig_id])
                        # display-name kısmını da düzeltelim
                        dn = elem.find("display-name")
                        if dn is not None: dn.text = TIVIBU_CHANNELS[orig_id]
                        master_root.append(elem)
                
                if elem.tag == "programme":
                    orig_id = elem.get("channel")
                    if orig_id in TIVIBU_CHANNELS:
                        elem.set("channel", TIVIBU_CHANNELS[orig_id])
                        master_root.append(elem)
        print("✅ Tivibu ve TİVİ6 başarıyla eklendi.")
    except Exception as e:
        print(f"⚠️ Tivibu/TİVİ6 hatası: {e}")

def create_master():
    master_root = ET.Element("tv", {"generator-info-name": "Weekly Master Scraper"})

    # 1. Türksat
    fetch_turksat_weekly(master_root)

    # 2. Yabancılar
    for country, url in SOURCES.items():
        print(f"🌍 {country} verisi işleniyor...")
        try:
            resp = requests.get(url, timeout=60)
            with gzip.GzipFile(fileobj=io.BytesIO(resp.content)) as f:
                context = ET.iterparse(f, events=("end",))
                for _, elem in context:
                    if elem.tag == "channel":
                        orig_id = elem.get("id")
                        if orig_id in WANTED_CHANNELS:
                            elem.set("id", WANTED_CHANNELS[orig_id])
                            master_root.append(elem)
                    
                    if elem.tag == "programme":
                        orig_id = elem.get("channel")
                        if orig_id in WANTED_CHANNELS:
                            elem.set("channel", WANTED_CHANNELS[orig_id])
                            master_root.append(elem)
        except Exception as e:
            print(f"⚠️ {country} hatası: {e}")

    # 3. Tivibu Spor & TİVİ6
    fetch_tivibu_spor(master_root)

    # 保存 (Save)
    os.makedirs("epg", exist_ok=True)
    tree = ET.ElementTree(master_root)
    xml_path = "epg/master_epg.xml"
    
    tree.write(xml_path, encoding="utf-8", xml_declaration=True)
    with open(xml_path, 'rb') as f_in, gzip.open(xml_path + ".gz", 'wb') as f_out:
        f_out.writelines(f_in)
    
    print("🚀 Tüm kaynaklar birleştirildi. Haftalık Master EPG Hazır!")

if __name__ == "__main__":
    create_master()
