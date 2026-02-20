import requests
import gzip
import xml.etree.ElementTree as ET
import io
import os
from datetime import datetime, timedelta

# --- TÜRKSAT DİNAMİK URL AYARI ---
# GitHub sunucusu UTC kullanır, Türkiye saatine (+3) çevirip bugünün gününü alıyoruz (Örn: "20")
tr_time = datetime.utcnow() + timedelta(hours=3)
today_day = tr_time.strftime("%d")
TURKSAT_JSON_URL = f"https://www.turksatkablo.com.tr/userUpload/EPG/{today_day}.json"

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

def create_master():
    # 1. Boş bir XML kökü oluştur (Çünkü Türksat artık JSON'dan gelecek)
    master_root = ET.Element("tv", {"generator-info-name": "CustomEPG"})

    # 2. Türksat JSON Verisini Çek ve XML'e Çevir (Önceki projendeki mantık)
    print(f"🇹🇷 Türksat verisi çekiliyor ({today_day}.json)...")
    try:
        r = requests.get(TURKSAT_JSON_URL, timeout=30)
        if r.status_code == 200:
            data = r.json()
            for item in data:
                # Kanal Bilgisi (Eğer henüz eklenmediyse)
                channel_id = item.get("KanalAd", "Bilinmiyor")
                # Basit bir kanal ekleme mantığı
                chan_elem = ET.SubElement(master_root, "channel", id=channel_id)
                ET.SubElement(chan_elem, "display-name").text = channel_id

                # Program Bilgisi
                prog = ET.SubElement(master_root, "programme", {
                    "start": item.get("BaslangicTarih", "").replace("-", "").replace(":", "").replace("T", "") + " +0300",
                    "stop": item.get("BitisTarih", "").replace("-", "").replace(":", "").replace("T", "") + " +0300",
                    "channel": channel_id
                })
                ET.SubElement(prog, "title", lang="tr").text = item.get("Ad", "")
                ET.SubElement(prog, "desc", lang="tr").text = item.get("Aciklama", "")
        else:
            print(f"⚠️ Türksat JSON bulunamadı (Kod: {r.status_code})")
    except Exception as e:
        print(f"⚠️ Türksat hatası: {e}")

    # 3. Yabancı Kaynakları İşle (Aynen devam)
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
    tree.write("epg/master_epg.xml", encoding="utf-8", xml_declaration=True)
    
    with open("epg/master_epg.xml", 'rb') as f_in, gzip.open("epg/master_epg.xml.gz", 'wb') as f_out:
        f_out.writelines(f_in)
    
    print("🚀 Master EPG Güncellendi!")

if __name__ == "__main__":
    create_master()
