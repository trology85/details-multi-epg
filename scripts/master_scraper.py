import requests
import gzip
import xml.etree.ElementTree as ET
import re
from bs4 import BeautifulSoup
import io
import os
from datetime import datetime, timedelta
import urllib3
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

# --- YENI KAYNAK KANALLARI (Tivibu & Tivi6) ---
TIVIBU_CHANNELS = {
    "TİVİBU.SPOR.1.tr": "TİVİBU SPOR 1",
    "TİVİBU.SPOR.2.tr": "TİVİBU SPOR 2",
    "TİVİBU.SPOR.3.tr": "TİVİBU SPOR 3",
    "TİVİBU.SPOR.4.tr": "TİVİBU SPOR 4",
    "TİVİ6.tr": "Tivi6",
    "TİVİ.6.tr": "TİVİ6"
}

DESC_TARGET_CHANNELS = {
    "trt 1",
    "star",
    "atv",
    "show tv",
    "kanal d",
    "now tv",
    "beyaz tv",
    "tv 8",
    "360 tv",
    "tv 2",
}

CHANNEL_ALIASES = {
    "trt1": "trt 1",
    "trt 1": "trt 1",

    "star": "star",
    "atv": "atv",

    "show": "show tv",
    "show tv": "show tv",

    "kanal d": "kanal d",

    "now": "now tv",
    "now tv": "now tv",
    "fox": "now tv",

    "beyaz": "beyaz tv",
    "beyaz tv": "beyaz tv",

    "tv8": "tv 8",
    "tv 8": "tv 8",

    "360": "360 tv",
    "360 tv": "360 tv",

    "tv2": "tv 2",
    "tv 2": "tv 2",
}

description_cache = {}

def normalize_channel_name(name: str) -> str:
    text = html_lib.unescape(name or "").lower()
    text = text.replace(".", " ").replace("-", " ")
    text = re.sub(r"\bhd\b", "", text)
    text = re.sub(r"\bsd\b", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return CHANNEL_ALIASES.get(text, text)

def should_fetch_desc(channel_name: str) -> bool:
    return normalize_channel_name(channel_name) in DESC_TARGET_CHANNELS
    
def get_program_detail(prog_id, target_date, channel_id, expected_channel_name):
    if not prog_id or not channel_id:
        return None

    cache_key = (str(prog_id), str(channel_id), target_date.strftime("%Y%m%d"))
    if cache_key in description_cache:
        return description_cache[cache_key]

    d = target_date.strftime("%d").lstrip("0")
    m = target_date.strftime("%m").lstrip("0")
    y = target_date.strftime("%Y")

    detail_url = (
        f"https://www.turksatkablo.com.tr/"
        f"yayin-akisi-program-detay.aspx?d={d}&m={m}&y={y}&kID={channel_id}&eID={prog_id}"
    )

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Referer": "https://www.turksatkablo.com.tr/yayin-akisi.aspx",
    }

    try:
        resp = requests.get(detail_url, headers=headers, verify=False, timeout=10)
        if resp.status_code != 200:
            description_cache[cache_key] = None
            return None

        raw_html = resp.text

        chan_match = re.search(r"<h2>(.*?)</h2>", raw_html, re.DOTALL | re.IGNORECASE)
        if chan_match:
            found_channel = normalize_channel_name(re.sub("<[^<]+?>", "", chan_match.group(1)))
            expected_channel = normalize_channel_name(expected_channel_name)
            if found_channel != expected_channel:
                if found_channel not in expected_channel and expected_channel not in found_channel:
                    description_cache[cache_key] = None
                    return None

        desc_match = re.search(r"<p>(.*?)</p>", raw_html, re.DOTALL | re.IGNORECASE)
        if not desc_match:
            description_cache[cache_key] = None
            return None

        clean_desc = desc_match.group(1).strip()
        clean_desc = re.sub(r"<[^<]+?>", "", clean_desc)
        clean_desc = html_lib.unescape(clean_desc)
        clean_desc = re.sub(r"\s+", " ", clean_desc).strip()

        if len(clean_desc) > 5:
            print(f"      ↳ 📝 {expected_channel_name} için detay başarıyla alındı.")
            description_cache[cache_key] = clean_desc
            return clean_desc

    except Exception as e:
        print(f"      ⚠️ Bağlantı hatası ({expected_channel_name}): {e}")

    description_cache[cache_key] = None
    return None

def fetch_turksat_weekly(master_root):
    tr_now = datetime.utcnow() + timedelta(hours=3)
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.turksatkablo.com.tr/yayin-akisi.aspx",
    }

    print("🇹🇷 Türksat Haftalık Tarama Başlatıldı...")

    for i in range(7):
        target_date = tr_now + timedelta(days=i)
        day_str = target_date.strftime("%d").lstrip("0")
        url = f"https://www.turksatkablo.com.tr/userUpload/EPG/{day_str}.json"

        try:
            r = requests.get(url, headers=headers, verify=False, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if "k" in data:
                    print(f"✅ {target_date.strftime('%d.%m.%Y')} eklendi.")
                    for channel in data.get("k", []):
                        chan_name = channel.get("n", "Unknown").strip()
                        chan_id = chan_name.replace(" ", ".")
                        chan_kID = channel.get("i")
                        fetch_desc_for_this_channel = should_fetch_desc(chan_name)
                        if i == 0:
                            print(f"KANAL DEBUG: {chan_name!r} -> {normalize_channel_name(chan_name)!r} -> desc={fetch_desc_for_this_channel}")

                        if i == 0:
                            c_elem = ET.SubElement(master_root, "channel", id=chan_id)
                            ET.SubElement(c_elem, "display-name").text = chan_name

                        date_prefix = target_date.strftime("%Y%m%d")

                        for prog in channel.get("p", []):
                            start_time = prog.get("c", "").replace(":", "")
                            stop_time = prog.get("d", "").replace(":", "")

                            current_stop_prefix = date_prefix
                            if int(stop_time) < int(start_time):
                                next_day = target_date + timedelta(days=1)
                                current_stop_prefix = next_day.strftime("%Y%m%d")

                            start = date_prefix + start_time + "00+0300"
                            stop = current_stop_prefix + stop_time + "00+0300"

                            p_elem = ET.SubElement(
                                master_root,
                                "programme",
                                start=start,
                                stop=stop,
                                channel=chan_id
                            )

                            title = prog.get("b", "Yayın Akışı")
                            ET.SubElement(p_elem, "title", lang="tr").text = title

                            if fetch_desc_for_this_channel and chan_kID:
                                prog_eID = prog.get("i")
                                if prog_eID:
                                    description = get_program_detail(
                                        prog_eID,
                                        target_date,
                                        chan_kID,
                                        chan_name
                                    )
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
        
def fetch_idman_tv(master_root):
    url = "https://idmantv.az/az/program"
    headers = {"User-Agent": "Mozilla/5.0"}
    chan_id = "Idman.TV"

    print("🇦 İdman TV verisi çekiliyor...")

    try:
        resp = requests.get(url, headers=headers, verify=False, timeout=20)
        if resp.status_code != 200:
            print(f"⚠️ İdman TV HTTP hatası: {resp.status_code}")
            return

        soup = BeautifulSoup(resp.text, "html.parser")
        day_cards = soup.find_all("div", class_="day-card")

        if not day_cards:
            print("⚠️ İdman TV day-card bulunamadı.")
            return

        parsed_items = []

        for card in day_cards:
            title_el = card.find("h3", class_="day-title")
            notes_el = card.find("div", class_="day-notes")

            if not title_el or not notes_el:
                continue

            title_text = title_el.get_text(" ", strip=True)
            date_match = re.search(r"(\d{2}\.\d{2}\.\d{4})", title_text)
            if not date_match:
                continue

            base_date = datetime.strptime(date_match.group(1), "%d.%m.%Y")

            p_el = notes_el.find("p")
            if not p_el:
                continue

            for br in p_el.find_all("br"):
                br.replace_with("\n")

            raw_text = p_el.get_text("\n", strip=True)
            lines = [line.strip() for line in raw_text.split("\n") if line.strip()]

            current_day = base_date
            prev_minutes = None

            for line in lines:
                m = re.match(r"^(\d{2}):(\d{2})\s+(.+)$", line)
                if not m:
                    continue

                hh = int(m.group(1))
                mm = int(m.group(2))
                title = m.group(3).strip()

                total_minutes = hh * 60 + mm

                # Saat geri sardıysa ertesi güne geç
                if prev_minutes is not None and total_minutes < prev_minutes:
                    current_day += timedelta(days=1)

                # Önce Azerbaycan saatiyle oluştur
                source_dt = current_day.replace(hour=hh, minute=mm, second=0, microsecond=0)

                # Türkiye saati için 1 saat geri al
                turkey_dt = source_dt - timedelta(hours=1)

                parsed_items.append((turkey_dt, title))
                prev_minutes = total_minutes

        if not parsed_items:
            print("⚠️ İdman TV için programme üretilemedi.")
            return

        parsed_items.sort(key=lambda x: x[0])

        c_elem = ET.SubElement(master_root, "channel", id=chan_id)
        ET.SubElement(c_elem, "display-name").text = "İdman TV"
        ET.SubElement(c_elem, "display-name").text = "Idman TV"

        for i, (start_dt, title) in enumerate(parsed_items):
            if i + 1 < len(parsed_items):
                stop_dt = parsed_items[i + 1][0]
            else:
                stop_dt = start_dt + timedelta(hours=1)

            start = start_dt.strftime("%Y%m%d%H%M%S") + "+0300"
            stop = stop_dt.strftime("%Y%m%d%H%M%S") + "+0300"

            p_elem = ET.SubElement(
                master_root,
                "programme",
                start=start,
                stop=stop,
                channel=chan_id
            )
            ET.SubElement(p_elem, "title", lang="tr").text = title

        print(f"✅ İdman TV başarıyla eklendi. ({len(parsed_items)} programme)")

    except Exception as e:
        print(f"⚠️ İdman TV hatası: {e}")

def create_master():
    master_root = ET.Element("tv", {"generator-info-name": "Weekly Master Scraper"})

    # 1. Türksat
    fetch_turksat_weekly(master_root)
    fetch_idman_tv(master_root)

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
