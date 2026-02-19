import requests
import gzip
import xml.etree.ElementTree as ET
import io
import os

# --- AYARLAR ---
# Senin ilk projendeki Türksat XML linki
TURKSAT_XML_URL = "https://raw.githubusercontent.com/trology85/iptv-epg-turkey/main/epg/turksat_epg.xml"

# EPGShare Kaynakları
SOURCES = {
    "DE": "https://epgshare01.online/epgshare01/epg_ripper_DE1.xml.gz",
    "FR": "https://epgshare01.online/epgshare01/epg_ripper_FR1.xml.gz",
    "GR": "https://epgshare01.online/epgshare01/epg_ripper_GR1.xml.gz"
}

# --- KANAL WHITELIST (FİLTRE) ---
# EPGShare'den sadece bu ID'ye sahip olanları alacağız.
# 'EPGShare_ID': 'Senin_Uygulamandaki_ID'
WANTED_CHANNELS = {
    # Alman Kanalları
    "RTL.de": "RTL", "ProSieben.de": "Pro7", "Sat1.de": "Sat1", "Vox.de": "Vox", "ZDF.de": "ZDF",
    # Fransız Kanalları
    "TF1.fr": "TF1", "M6.fr": "M6", "France2.fr": "France.2", "CanalPlus.fr": "Canal.Plus",
    # Yunan Kanalları
    "ERT1.gr": "ERT1", "Mega.gr": "Mega", "Ant1.gr": "Ant1", "Skai.gr": "Skai"
}

def create_master():
    # 1. Türksat XML'ini ana temel (base) olarak indir
    print("🇹🇷 Türksat verisi çekiliyor...")
    r = requests.get(TURKSAT_XML_URL)
    master_root = ET.fromstring(r.content)

    # 2. Yabancı Kaynakları İşle
    for country, url in SOURCES.items():
        print(f"🌍 {country} verisi işleniyor: {url}")
        try:
            resp = requests.get(url, timeout=60)
            with gzip.GzipFile(fileobj=io.BytesIO(resp.content)) as f:
                context = ET.iterparse(f, events=("end",))
                for _, elem in context:
                    # Sadece istediğimiz kanalları ekle
                    if elem.tag == "channel":
                        orig_id = elem.get("id")
                        if orig_id in WANTED_CHANNELS:
                            elem.set("id", WANTED_CHANNELS[orig_id])
                            master_root.append(elem)
                    
                    # Sadece istediğimiz programları ekle
                    if elem.tag == "programme":
                        orig_id = elem.get("channel")
                        if orig_id in WANTED_CHANNELS:
                            elem.set("channel", WANTED_CHANNELS[orig_id])
                            master_root.append(elem)
                    
                    # Belleği temiz tutmak için işi biten elemanı sil
                    # elem.clear() -> Bu satır master_root'a eklediğimizi de silebilir, 
                    # o yüzden dikkatli kullanılmalı.
        except Exception as e:
            print(f"⚠️ {country} hatası: {e}")

    # 3. Kaydet
    os.makedirs("epg", exist_ok=True)
    tree = ET.ElementTree(master_root)
    tree.write("epg/master_epg.xml", encoding="utf-8", xml_declaration=True)
    
    with open("epg/master_epg.xml", 'rb') as f_in, gzip.open("epg/master_epg.xml.gz", 'wb') as f_out:
        f_out.writelines(f_in)
    
    print("🚀 Master EPG Hazır!")

if __name__ == "__main__":
    create_master()
