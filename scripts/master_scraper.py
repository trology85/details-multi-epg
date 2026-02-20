import requests
import gzip
import xml.etree.ElementTree as ET
import io
import os
from datetime import datetime, timedelta
import urllib3

# Güvenlik uyarılarını kapat
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- AYARLAR ---
# EPGShare Kaynakları
SOURCES = {
    "DE": "https://epgshare01.online/epgshare01/epg_ripper_DE1.xml.gz",
    "FR": "https://epgshare01.online/epgshare01/epg_ripper_FR1.xml.gz",
    "GR": "https://epgshare01.online/epgshare01/epg_ripper_GR1.xml.gz"
}

# --- KANAL WHITELIST ---
WANTED_CHANNELS = {
    "RTL.de": "RTL", "ProSieben.de": "Pro7", "SAT.1.de": "Sat1", "VOX.de": "Vox", "ZDF.de": "ZDF",
    "TF1.fr": "TF1", "M6.fr": "M6", "France2.fr": "France.2", "CanalPlus.fr": "Canal.Plus", "RTL.9.fr": "RTL 9",
    "ERT1.gr": "ERT1", "Mega.gr": "Mega", "Ant1.gr": "ANT1.gr", "Skai.gr": "Skai"
}

def fetch_turksat():
    # Türkiye saatine göre bugünün JSON dosyasını bul (Örn: 20.json)
    tr_time = datetime.utcnow() + timedelta(hours=3)
    day_str = tr_time.strftime("%d").lstrip('0')
    url = f"https://www.turksatkablo.com.tr/userUpload/EPG/{day_str}.json"
    
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        print(f"📡 Türksat Canlı Verisi Çekiliyor: {url}")
        r = requests.get(url, headers=headers, verify=False, timeout=15)
        if r.status_code == 200:
            return r.json(), tr_time
    except:
        return None, None
    return None, None

def create_master():
    # 1. Ana XML Kökünü Oluştur
    master_root = ET.Element("tv", {"generator-info-name": "Master Scraper"})

    # 2. Önce Türksat'ı JSON'dan çekip XML'e çevirerek ekle
    data, actual_date = fetch_turksat()
    if data and 'k' in data:
        print("✅ Türksat JSON başarıyla işleniyor...")
        for channel in data.get('k', []):
            chan_name = channel.get('n', 'Unknown')
            chan_id = chan_name.replace(" ", ".")
            
            c_elem = ET.SubElement(master_root, "channel", id=chan_id)
            ET.SubElement(c_elem, "display-name").text = chan_name

            for prog in channel.get('p', []):
                start = actual_date.strftime('%Y%m%d') + prog.get('c', '').replace(":", "") + "00 +0300"
                stop = actual_date.strftime('%Y%m%d') + prog.get('d', '').replace(":", "") + "00 +0300"
                
                p_elem = ET.SubElement(master_root, "programme", start=start, stop=stop, channel=chan_id)
                ET.SubElement(p_elem, "title", lang="tr").text = prog.get('b', 'Yayın Akışı')
    else:
        print("⚠️ Türksat verisi alınamadı, boş geçiliyor.")

    # 3. Yabancı Kaynakları İşle
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

    # 4. Kaydet
    os.makedirs("epg", exist_ok=True)
    tree = ET.ElementTree(master_root)
    xml_path = "epg/master_epg.xml"
    
    tree.write(xml_path, encoding="utf-8", xml_declaration=True)
    with open(xml_path, 'rb') as f_in, gzip.open(xml_path + ".gz", 'wb') as f_out:
        f_out.writelines(f_in)
    
    print("🚀 Master EPG (Türksat JSON + Yabancı XML) Hazır!")

if __name__ == "__main__":
    create_master()
