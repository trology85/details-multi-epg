import requests
import gzip
import xml.etree.ElementTree as ET
import io
import os
from datetime import datetime, timedelta
import urllib3
from bs4 import BeautifulSoup
import re
import html as html_lib

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
            raw_html = resp.text
            chan_match = re.search(r'<h2>(.*?)</h2>', raw_html)
            if chan_match:
                found_channel = chan_match.group(1).strip().lower()
                expected_clean = expected_channel_name.lower().replace(" hd", "").strip()
                
                if expected_clean in found_channel or found_channel in expected_clean:
                    desc_match = re.search(r'<p>(.*?)</p>', raw_html, re.DOTALL)
                    if desc_match:
                        clean_desc = desc_match.group(1).strip()
                        clean_desc = re.sub('<[^<]+?>', '', clean_desc)
                        clean_desc = html_lib.unescape(clean_desc)
                        
                        if len(clean_desc) > 5:
                            print(f"      ↳ 📝 {expected_channel_name} için detay başarıyla alındı.")
                            return clean_desc
    except Exception as e:
        print(f"      ⚠️ Bağlantı hatası ({expected_channel_name}): {e}")
        
    return None

def fetch_idman_tv(master_root):
    url = "https://idmantv.az/az/program"
    headers = {'User-Agent': 'Mozilla/5.0'}
    chan_id = "Idman.TV.az"
    
    print("🇦🇿 İdman TV Kazıma ve Düzeltme Başlatıldı...")
    
    try:
        r = requests.get(url, headers=headers, verify=False, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.content, 'html.parser')
            
            # 1. Kanal tanımı HER ZAMAN programme'lardan önce eklenir
            c_elem = ET.SubElement(master_root, "channel", id=chan_id)
            ET.SubElement(c_elem, "display-name").text = "İdman TV"

            day_cards = soup.find_all('div', class_='day-card')
            programmes_buffer = [] # Programları önce burada topluyoruz

            for card in day_cards:
                title_text = card.find('h3', class_='day-title').get_text(strip=True)
                date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})', title_text)
                if not date_match: continue
                
                current_date_str = date_match.group(1)
                formatted_date = datetime.strptime(current_date_str, '%d.%m.%Y')

                notes_div = card.find('div', class_='day-notes')
                if not notes_div or not notes_div.p: continue
                
                raw_text = notes_div.p.get_text('\n')
                lines = [line.strip() for line in raw_text.split('\n') if line.strip()]

                for i, line in enumerate(lines):
                    match = re.match(r'^(\d{2}:\d{2})\s+(.*)', line)
                    if match:
                        time_str = match.group(1).replace(":", "")
                        title_val = match.group(2)
                        
                        # BOŞLUK KALDIRILDI: "00+0300" (XMLTV Standardı)
                        start_raw = formatted_date.strftime('%Y%m%d') + time_str + "00+0300"
                        
                        if i + 1 < len(lines):
                            next_match = re.match(r'^(\d{2}:\d{2})', lines[i+1])
                            if next_match:
                                next_time_str = next_match.group(1).replace(":", "")
                                if int(next_time_str) < int(time_str):
                                    stop_day = formatted_date + timedelta(days=1)
                                    stop_raw = stop_day.strftime('%Y%m%d') + next_time_str + "00+0300"
                                else:
                                    stop_raw = formatted_date.strftime('%Y%m%d') + next_time_str + "00+0300"
                            else:
                                stop_raw = formatted_date.strftime('%Y%m%d') + "235900+0300"
                        else:
                            stop_raw = formatted_date.strftime('%Y%m%d') + "235900+0300"

                        # Hemen XML'e eklemek yerine listeye alıyoruz
                        programmes_buffer.append((start_raw, stop_raw, title_val))
            
            # 2. KRONOLOJİK SIRALAMA (En kritik düzeltme)
            programmes_buffer.sort(key=lambda x: x[0])

            # 3. Sıralı veriyi XML'e yazıyoruz
            for start_t, stop_t, title_val in programmes_buffer:
                p_elem = ET.SubElement(master_root, "programme", 
                                      start=start_t, 
                                      stop=stop_t, 
                                      channel=chan_id)
                ET.SubElement(p_elem, "title", lang="az").text = title_val
            
            print("✅ İdman TV saat hataları düzeltilerek eklendi.")
    except Exception as e:
        print(f"⚠️ İdman TV hatası: {e}")

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
                            
                            if not progs and i == 0:
                                print(f"      ⚠️ Uyarı: {chan_name_orig} için program listesi (p) boş!")

                            for prog in progs:
                                start_time = prog.get('c', '').replace(":", "")
                                stop_time = prog.get('d', '').replace(":", "")
                                current_stop_prefix = date_prefix
                                
                                if int(stop_time) < int(start_time):
                                    next_day = target_date + timedelta(days=1)
                                    current_stop_prefix = next_day.strftime('%Y%m%d')

                                # BOŞLUK KALDIRILDI
                                start = date_prefix + start_time + "00+0300"
                                stop = current_stop_prefix + stop_time + "00+0300"
                                
                                p_elem = ET.SubElement(master_root, "programme", start=start, stop=stop, channel=chan_id)
                                title = prog.get('b', 'Yayın Akışı')
                                ET.SubElement(p_elem, "title", lang="tr").text = title
                                
                                prog_eID = prog.get('i') 
                                if prog_eID and chan_kID:
                                    description = get_program_detail(prog_eID, target_date, chan_kID, chan_name_orig)
                                    if description:
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
    fetch_idman_tv(master_root)

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
