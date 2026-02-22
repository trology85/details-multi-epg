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

def fetch_turksat_weekly(master_root):
    # Türkiye saatine göre bugün
    tr_now = datetime.utcnow() + timedelta(hours=3)
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    print("🇹🇷 Türksat Haftalık Tarama Başlatıldı (7 Gün)...")
    
    # Bugün dahil gelecek 7 günü tara
    for i in range(7):
        target_date = tr_now + timedelta(days=i)
        day_str = target_date.strftime("%d").lstrip('0')
        url = f"https://www.turksatkablo.com.tr/userUpload/EPG/{day_str}.json"
        
        try:
            r = requests.get(url, headers=headers, verify=False, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if 'k' in data:
                    print(f"✅ {target_date.strftime('%d.%m.%Y')} verisi eklendi.")
                    for channel in data.get('k', []):
                        chan_name = channel.get('n', 'Unknown')
                        chan_id = chan_name.replace(" ", ".")
                        
                        # Kanalı sadece ilk gün (bugün) için bir kez tanımla
                        if i == 0:
                            c_elem = ET.SubElement(master_root, "channel", id=chan_id)
                            ET.SubElement(c_elem, "display-name").text = chan_name

                        # Programları ekle
                        date_prefix = target_date.strftime('%Y%m%d')
                        for prog in channel.get('p', []):
                            start = date_prefix + prog.get('c', '').replace(":", "") + "00 +0300"
                            stop = date_prefix + prog.get('d', '').replace(":", "") + "00 +0300"
                            
                            p_elem = ET.SubElement(master_root, "programme", start=start, stop=stop, channel=chan_id)
                            ET.SubElement(p_elem, "title", lang="tr").text = prog.get('b', 'Yayın Akışı')
            else:
                print(f"ℹ️ {target_date.strftime('%d.%m.%Y')} için henüz veri yok (Sunucu: {r.status_code})")
        except Exception as e:
            print(f"⚠️ {target_date.strftime('%d.%m.%Y')} taramasında hata: {e}")

def create_master():
    master_root = ET.Element("tv", {"generator-info-name": "Weekly Master Scraper"})

    # 1. Türksat Haftalık İşlemi
    fetch_turksat_weekly(master_root)

    # 2. Yabancı Kaynakları İşle (EPGShare zaten haftalık veri barındırır)
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

    # 3. Kaydet
    os.makedirs("epg", exist_ok=True)
    tree = ET.ElementTree(master_root)
    xml_path = "epg/master_epg.xml"
    
    tree.write(xml_path, encoding="utf-8", xml_declaration=True)
    with open(xml_path, 'rb') as f_in, gzip.open(xml_path + ".gz", 'wb') as f_out:
        f_out.writelines(f_in)
    
    print("🚀 Haftalık Master EPG Hazır!")

if __name__ == "__main__":
    create_master()
