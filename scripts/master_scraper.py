import requests
import gzip
import xml.etree.ElementTree as ET
import io
import os
from datetime import datetime, timedelta
import urllib3
import re

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

TIVIBU_CHANNELS = {
    "TİVİBU.SPOR.1.tr": "TİVİBU SPOR 1",
    "TİVİBU.SPOR.2.tr": "TİVİBU SPOR 2",
    "TİVİBU.SPOR.3.tr": "TİVİBU SPOR 3",
    "TİVİBU.SPOR.4.tr": "TİVİBU SPOR 4",
    "TİVİ6.tr": "Tivi6",
    "TİVİ.6.tr": "TİVİ6"
}

# --- DETAY ÇEKİLECEK HEDEF TÜRK KANALLARI ---
# Bu listedeki kanallar için Türksat sitesinden özel açıklama kazınacak.
DETAIL_CHANNELS = [
    "TRT 1", "ATV", "NOW", "SHOW TV", "KANAL D", "STAR", "TV8", "TV 8,5", 
    "BEYAZ TV", "KANAL 7", "CNBC-E", "TRT SPOR", "360 TV", "TLC", "DMAX", 
    "TV2", "TRT 2", "A2", "TRT BELGESEL"
]

# Açıklamaları hafızada tutmak için (Aynı program tekrar ederse tekrar internete gitmesin)
description_cache = {}

def get_program_detail(prog_id):
    """Türksat sitesinden program detayını çeken yardımcı fonksiyon"""
    if not prog_id: return None
    if prog_id in description_cache: return description_cache[prog_id]
    
    detail_url = f"https://www.turksatkablo.com.tr/yayin-akisi-detay.aspx?id={prog_id}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        # 2 saniye timeout verdik ki sistem takılmasın
        resp = requests.get(detail_url, headers=headers, verify=False, timeout=2)
        if resp.status_code == 200:
            # HTML içindeki açıklama kısmını basit bir Regex ile çekiyoruz
            match = re.search(r'<div class="program-detay">(.*?)</div>', resp.text, re.DOTALL)
            if match:
                desc = match.group(1).strip()
                # HTML taglarını temizle
                desc = re.sub('<[^<]+?>', '', desc)
                description_cache[prog_id] = desc
                return desc
    except:
        pass
    return None

# --- HEDEF TÜRK KANALLARI (Daha Garanti Liste) ---
DETAIL_CHANNELS = [
    "TRT 1", "ATV", "NOW", "SHOW TV", "KANAL D", "STAR", "TV8", "TV 8,5", 
    "BEYAZ TV", "KANAL 7", "CNBC-E", "TRT SPOR", "360 TV", "TLC", "DMAX", 
    "TV2", "TRT 2", "A2", "TRT BELGESEL", "TGRT HABER"
]

def fetch_turksat_weekly(master_root):
    tr_now = datetime.utcnow() + timedelta(hours=3)
    headers = {'User-Agent': 'Mozilla/5.0'}
    print("🇹🇷 Türksat Haftalık Zenginleştirilmiş Tarama Başlatıldı...")
    
    for i in range(7):
        target_date = tr_now + timedelta(days=i)
        day_str = target_date.strftime("%d").lstrip('0')
        url = f"https://www.turksatkablo.com.tr/userUpload/EPG/{day_str}.json"
        
        try:
            r = requests.get(url, headers=headers, verify=False, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if 'k' in data:
                    print(f"✅ {target_date.strftime('%d.%m.%Y')} işleniyor...")
                    for channel in data.get('k', []):
                        chan_name = channel.get('n', 'Unknown').strip()
                        # ID oluştururken boşlukları noktaya çeviriyoruz (XML standardı için)
                        chan_id = chan_name.replace(" ", ".")
                        
                        if i == 0:
                            c_elem = ET.SubElement(master_root, "channel", id=chan_id)
                            ET.SubElement(c_elem, "display-name").text = chan_name

                        date_prefix = target_date.strftime('%Y%m%d')
                        for prog in channel.get('p', []):
                            # ... (Zaman hesaplamaları aynı kalıyor) ...
                            start_time = prog.get('c', '').replace(":", "")
                            stop_time = prog.get('d', '').replace(":", "")
                            current_stop_prefix = date_prefix
                            if int(stop_time) < int(start_time):
                                next_day = target_date + timedelta(days=1)
                                current_stop_prefix = next_day.strftime('%Y%m%d')

                            start = date_prefix + start_time + "00 +0300"
                            stop = current_stop_prefix + stop_time + "00 +0300"
                            
                            p_elem = ET.SubElement(master_root, "programme", start=start, stop=stop, channel=chan_id)
                            ET.SubElement(p_elem, "title", lang="tr").text = prog.get('b', 'Yayın Akışı')
                            
                            # --- KRİTİK DÜZELTME BURADA ---
                            # Hem boşluklu hem noktalı halini kontrol et
                            if chan_name in DETAIL_CHANNELS or chan_id in DETAIL_CHANNELS:
                                prog_id = prog.get('i')
                                if prog_id:
                                    description = get_program_detail(prog_id)
                                    if description:
                                        # EPG verisinde <desc> ekle
                                        ET.SubElement(p_elem, "desc", lang="tr").text = description
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
    fetch_turksat_weekly(master_root)

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

    fetch_tivibu_spor(master_root)

    os.makedirs("epg", exist_ok=True)
    tree = ET.ElementTree(master_root)
    xml_path = "epg/master_epg.xml"
    
    tree.write(xml_path, encoding="utf-8", xml_declaration=True)
    with open(xml_path, 'rb') as f_in, gzip.open(xml_path + ".gz", 'wb') as f_out:
        f_out.writelines(f_in)
    
    print("🚀 Tüm kaynaklar birleştirildi. Haftalık Master EPG Hazır!")

if __name__ == "__main__":
    create_master()
