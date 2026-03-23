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

# --- HEDEF KANALLAR (Sitede Görünen En Sade Haller) ---
DETAIL_CHANNELS = [
    "trt 1", "atv", "now", "show", "kanal d", "star", "tv8", "tv 8,5", "tv8.5",
    "beyaz tv", "kanal 7", "cnbc", "trt spor", "360", "tlc", "dmax", 
    "teve2", "trt 2", "a2", "belgesel", "tgrt"
]

description_cache = {}

def get_program_detail(prog_id, target_date, channel_id):
    """
    Mozilla Network sekmesinden yakalanan yeni yapı:
    yayin-akisi-program-detay.aspx?d=GÜN&m=AY&y=YIL&kID=KANAL_ID&eID=PROGRAM_ID
    """
    if not prog_id or not channel_id:
        return None
        
    # Tarih parçalarını ayıklıyoruz (Başındaki sıfırları siliyoruz: 03 -> 3 gibi)
    d = target_date.strftime("%d").lstrip('0')
    m = target_date.strftime("%m").lstrip('0')
    y = target_date.strftime("%Y")
    
    # Senin bulduğun o tam link yapısı
    detail_url = f"https://www.turksatkablo.com.tr/yayin-akisi-program-detay.aspx?d={d}&m={m}&y={y}&kID={channel_id}&eID={prog_id}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,webp,*/*;q=0.8',
        'Referer': 'https://www.turksatkablo.com.tr/yayin-akisi.aspx',
        'Connection': 'keep-alive'
    }
    
    try:
        # SSL doğrulamayı (verify=False) açık bırakıyoruz hata almamak için
        resp = requests.get(detail_url, headers=headers, verify=False, timeout=10)
        if resp.status_code == 200:
            # HTML içindeki temiz metni alalım
            text = resp.text
            # Eğer 'program-detay' divi varsa içini al, yoksa genel metni temizle
            if "program-detay" in text:
                match = re.search(r'<div class="program-detay">(.*?)</div>', text, re.DOTALL)
                if match:
                    raw_content = match.group(1).strip()
                    # HTML etiketlerini ve boşlukları temizle
                    clean_desc = re.sub('<[^<]+?>', '', raw_content)
                    clean_desc = clean_desc.replace('&nbsp;', ' ').strip()
                    if len(clean_desc) > 5:
                        print(f"      ↳ 📝 Detay Başarılı ({prog_id}): {clean_desc[:35]}...")
                        return clean_desc
            else:
                # Div yoksa bile sayfadaki tüm yazıları temizleyip şansımızı deneyelim
                alt_clean = re.sub('<[^<]+?>', '', text).strip()
                if len(alt_clean) > 10:
                    return alt_clean
    except Exception as e:
        print(f"      ↳ ❌ Detay Hatası: {str(e)[:50]}")
    return None

def fetch_turksat_weekly(master_root):
    tr_now = datetime.utcnow() + timedelta(hours=3)
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    print("🇹🇷 Türksat Haftalık Detaylı Tarama Başlatıldı...")
    
    for i in range(7):
        target_date = tr_now + timedelta(days=i)
        day_str = target_date.strftime("%d").lstrip('0')
        url = f"https://www.turksatkablo.com.tr/userUpload/EPG/{day_str}.json"
        
        try:
            r = requests.get(url, headers=headers, verify=False, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if 'k' in data:
                    print(f"📅 {target_date.strftime('%d.%m.%Y')} işleniyor...")
                    for channel in data.get('k', []):
                        chan_name_orig = channel.get('n', '').strip()
                        chan_name_lower = chan_name_orig.lower()
                        chan_id = chan_name_orig.replace(" ", ".")
                        
                        if i == 0:
                            c_elem = ET.SubElement(master_root, "channel", id=chan_id)
                            ET.SubElement(c_elem, "display-name").text = chan_name_orig

                        # --- RADAR: Hedef kanal mı kontrol et ---
                        is_target = any(target in chan_name_lower for target in DETAIL_CHANNELS)
                        
                        # Sadece ilk günde hangi kanalları yakaladığımızı logda görelim
                        if is_target and i == 0:
                            print(f"   🎯 Hedef Yakalandı: {chan_name_orig}")

                        date_prefix = target_date.strftime('%Y%m%d')
                        for prog in channel.get('p', []):
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
                            
                            if is_target:
                                prog_id = prog.get('i')
                                if prog_id:
                                    description = get_program_detail(prog_id)
                                    if description:
                                        ET.SubElement(p_elem, "desc", lang="tr").text = description
        except Exception as e:
            print(f"⚠️ Türksat hatası: {e}")

# fetch_tivibu_spor ve create_master kısımları aynı kalıyor...

def fetch_turksat_weekly(master_root):
    # Türkiye saati (UTC+3)
    tr_now = datetime.utcnow() + timedelta(hours=3)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0',
        'Referer': 'https://www.turksatkablo.com.tr/yayin-akisi.aspx'
    }
    
    print("🇹🇷 Türksat Haftalık Zenginleştirilmiş Tarama Başlatıldı...")
    
    # 7 günlük döngü
    for i in range(7):
        target_date = tr_now + timedelta(days=i)
        # Gün bilgisini alıyoruz (Başındaki sıfırı siliyoruz: 05 -> 5 gibi)
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
                        # Türksat'ın kanal ID'si (Senin bulduğun kID parametresi için)
                        chan_kID = channel.get('i') 
                        
                        # XML standardı için boşlukları noktaya çevir
                        chan_id = chan_name_orig.replace(" ", ".")
                        
                        # Kanal bilgisini sadece ilk gün (i=0) ekliyoruz (Mükerrer olmasın diye)
                        if i == 0:
                            c_elem = ET.SubElement(master_root, "channel", id=chan_id)
                            ET.SubElement(c_elem, "display-name").text = chan_name_orig

                        # Bu kanal bizim detay çekeceğimiz listemizde var mı?
                        is_target = any(target in chan_name_lower for target in DETAIL_CHANNELS)
                        
                        if is_target and i == 0:
                            print(f"   🎯 Hedef Kanal Yakalandı: {chan_name_orig} (kID: {chan_kID})")

                        date_prefix = target_date.strftime('%Y%m%d')
                        
                        for prog in channel.get('p', []):
                            # Zaman hesaplamaları
                            start_time = prog.get('c', '').replace(":", "")
                            stop_time = prog.get('d', '').replace(":", "")
                            current_stop_prefix = date_prefix
                            
                            # Gece yarısı devrini kontrol et (Ertesi güne sarkma)
                            if int(stop_time) < int(start_time):
                                next_day = target_date + timedelta(days=1)
                                current_stop_prefix = next_day.strftime('%Y%m%d')

                            start = date_prefix + start_time + "00 +0300"
                            stop = current_stop_prefix + stop_time + "00 +0300"
                            
                            # Programme elementini oluştur
                            p_elem = ET.SubElement(master_root, "programme", start=start, stop=stop, channel=chan_id)
                            ET.SubElement(p_elem, "title", lang="tr").text = prog.get('b', 'Yayın Akışı')
                            
                            # --- DETAY ÇEKME AŞAMASI ---
                            if is_target:
                                # Programın ID'si (Senin bulduğun eID parametresi için)
                                prog_eID = prog.get('i') 
                                
                                if prog_eID and chan_kID:
                                    # Detay fonksiyonuna 3 parametreyi de gönderiyoruz
                                    description = get_program_detail(prog_eID, target_date, chan_kID)
                                    if description:
                                        # XML'e açıklamayı ekle
                                        ET.SubElement(p_elem, "desc", lang="tr").text = description

        except Exception as e:
            print(f"⚠️ Türksat hatası ({target_date.strftime('%d.%m')}): {e}")

def create_master():
    master_root = ET.Element("tv", {"generator-info-name": "Weekly Master Scraper"})
    fetch_turksat_weekly(master_root)
    for country, url in SOURCES.items():
        try:
            resp = requests.get(url, timeout=60)
            with gzip.GzipFile(fileobj=io.BytesIO(resp.content)) as f:
                context = ET.iterparse(f, events=("end",))
                for _, elem in context:
                    if elem.tag == "channel" and elem.get("id") in WANTED_CHANNELS:
                        elem.set("id", WANTED_CHANNELS[elem.get("id")])
                        master_root.append(elem)
                    if elem.tag == "programme" and elem.get("channel") in WANTED_CHANNELS:
                        elem.set("channel", WANTED_CHANNELS[elem.get("channel")])
                        master_root.append(elem)
        except: pass
    fetch_tivibu_spor(master_root)
    os.makedirs("epg", exist_ok=True)
    tree = ET.ElementTree(master_root)
    xml_path = "epg/master_epg.xml"
    tree.write(xml_path, encoding="utf-8", xml_declaration=True)
    with open(xml_path, 'rb') as f_in, gzip.open(xml_path + ".gz", 'wb') as f_out:
        f_out.writelines(f_in)
    print("🚀 Haftalık Master EPG Hazır!")

if __name__ == "__main__":
    create_master()
