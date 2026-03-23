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

DETAIL_CHANNELS = [
    "trt 1", "atv", "now", "show", "kanal d", "star", "tv8", "tv 8,5", "tv8.5",
    "beyaz tv", "kanal 7", "cnbc", "trt spor", "360", "tlc", "dmax", 
    "teve2", "trt 2", "a2", "belgesel", "tgrt"
]

description_cache = {}

def get_program_detail(prog_id, target_date, channel_id, expected_channel_name):
    if not prog_id or not channel_id:
        return None
    
    d = target_date.strftime("%d").lstrip('0')
    m = target_date.strftime("%m").lstrip('0')
    y = target_date.strftime("%Y")
    
    detail_url = f"https://www.turksatkablo.com.tr/yayin-akisi-program-detay.aspx?d={d}&m={m}&y={y}&kID={channel_id}&eID={prog_id}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'Referer': 'https://www.turksatkablo.com.tr/yayin-akisi.aspx'
    }
    
    try:
        resp = requests.get(detail_url, headers=headers, verify=False, timeout=10)
        if resp.status_code == 200:
            html = resp.text
            
            # 1. Adım: Kanal İsmi Doğrulama (İlk <h2> etiketine bakıyoruz)
            # Senin attığın kodda: <h2>TV 8</h2>
            chan_match = re.search(r'<h2>(.*?)</h2>', html)
            if chan_match:
                found_channel = chan_match.group(1).strip().lower()
                # Beklenen kanal ismi (örn: "tv 8") gelenin içindeyse devam et
                if expected_channel_name.lower() in found_channel or found_channel in expected_channel_name.lower():
                    
                    # 2. Adım: Açıklamayı Çek ( <p> etiketinin içindeki metin )
                    desc_match = re.search(r'<p>(.*?)</p>', html, re.DOTALL)
                    if desc_match:
                        clean_desc = desc_match.group(1).strip()
                        # HTML kalıntılarını temizle (&#252; gibi karakterler için)
                        clean_desc = re.sub('<[^<]+?>', '', clean_desc)
                        import html as html_lib
                        clean_desc = html_lib.unescape(clean_desc)
                        
                        if len(clean_desc) > 10:
                            print(f"      ↳ 📝 {expected_channel_name} Detayı Alındı: {clean_desc[:40]}...")
                            return clean_desc
    except Exception as e:
        print(f"      ⚠️ Detay Hatası: {e}")
    return None

def fetch_turksat_weekly(master_root):
    tr_now = datetime.utcnow() + timedelta(hours=3)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0',
        'Referer': 'https://www.turksatkablo.com.tr/yayin-akisi.aspx'
    }
    
    print("🇹🇷 Türksat Haftalık Zenginleştirilmiş Tarama Başlatıldı...")
    
    for i in range(7):
        target_date = tr_now + timedelta(days=i)
        day_str = target_date.strftime("%d").lstrip('0')
        url = f"https://www.turksatkablo.com.tr/userUpload/EPG/{day_str}.json"
        
        try:
            r = requests.get(url, headers=headers, verify=False, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if 'k' in data:
                    print(f"📅 {target_date.strftime('%d.%m.%Y')} işleniyor...")
                    for channel in data.get('k', []):
                        chan_name_orig = channel.get('n', '').strip()
                        chan_name_lower = chan_name_orig.lower()
                        chan_kID = channel.get('i') 
                        chan_id = chan_name_orig.replace(" ", ".")
                        
                        if i == 0:
                            c_elem = ET.SubElement(master_root, "channel", id=chan_id)
                            ET.SubElement(c_elem, "display-name").text = chan_name_orig

                        is_target = any(target in chan_name_lower for target in DETAIL_CHANNELS)
                        
                        if is_target:
                            if i == 0:
                                print(f"   🎯 Hedef Kanal: {chan_name_orig} (kID: {chan_kID})")
                            
                            date_prefix = target_date.strftime('%Y%m%d')
                            progs = channel.get('p', [])
                            
                            # EĞER PROGRAM LİSTESİ BOŞSA LOG BASALIM
                            if not progs and i == 0:
                                print(f"      ⚠️ Uyarı: {chan_name_orig} için program listesi (p) boş!")

                            for prog in progs:
                                start_time = prog.get('c', '').replace(":", "")
                                stop_time = prog.get('d', '').replace(":", "")
                                current_stop_prefix = date_prefix
                                
                                if int(stop_time) < int(start_time):
                                    next_day = target_date + timedelta(days=1)
                                    current_stop_prefix = next_day.strftime('%Y%m%d')

                                start = date_prefix + start_time + "00 +0300"
                                stop = current_stop_prefix + stop_time + "00 +0300"
                                
                                p_elem = ET.SubElement(master_root, "programme", start=start, stop=stop, channel=chan_id)
                                title = prog.get('b', 'Yayın Akışı')
                                ET.SubElement(p_elem, "title", lang="tr").text = title
                                
                                # PROGRAM DETAY SORGUSU
                                prog_eID = prog.get('i') 
                                if prog_eID and chan_kID:
                                    description = get_program_detail(prog_eID, target_date, chan_kID)
                                    if description:
                                        ET.SubElement(p_elem, "desc", lang="tr").text = description
                                # EĞER ID VAR AMA DETAY ÇIKMIYORSA LOG BASALIM (i=0 ve ilk 3 program için)
                                elif i == 0:
                                     pass # Log kirliliği olmasın diye sadece ID kontrolü yapıyoruz
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
