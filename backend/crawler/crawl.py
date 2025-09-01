
import argparse
import json
import re
import time
from collections import deque
from urllib.parse import urljoin, urlparse
import os
from pathlib import Path
from urllib.robotparser import RobotFileParser
import logging

import requests
from bs4 import BeautifulSoup, NavigableString

# Setup logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.FileHandler("crawler.log"),
                        logging.StreamHandler()
                    ])

# Helper to filter out common boilerplate tags
def is_boilerplate(tag):
    return tag.name in ['header', 'footer', 'nav', 'aside', 'script', 'style', 'noscript', 'iframe', 'template']

# Normalize URLs to avoid duplicates
def normalize_url(url):
    url = url.lower().strip()
    parsed = urlparse(url)
    # Remove tracking parameters and fragments
    clean_params = '&'.join(
        p for p in parsed.query.split('&')
        if not p.startswith(('utm_', 'gclid', 'fbclid'))
    )
    return parsed._replace(query=clean_params, fragment="").geturl()

# Extract image data and its context
def extract_images(soup, base_url):
    images = []
    for img in soup.select('main img, article img'): # Focus on content areas
        src = img.get('src') or img.get('data-src')

        # Handle srcset
        srcset = img.get('srcset')
        if srcset:
            # A simple approach: take the first URL from srcset
            # A more advanced approach would parse the srcset and choose the best quality
            src = srcset.split(',')[0].strip().split(' ')[0]

        # Handle picture elements
        if img.parent.name == 'picture':
            for source in img.parent.find_all('source'):
                if source.get('srcset'):
                    src = source.get('srcset').split(',')[0].strip().split(' ')[0]
                    break

        if not src:
            continue

        # Resolve relative URLs
        src = urljoin(base_url, src)
        alt = img.get('alt', '')

        # Find context: nearest headers and surrounding text
        header_lineage = [h.get_text(strip=True) for h in img.find_previous_siblings(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])]
        header_lineage.reverse()

        # Context snippet from surrounding text
        context_before = ""
        for sibling in img.parent.find_previous_siblings(limit=2):
            if not isinstance(sibling, NavigableString):
                context_before = sibling.get_text(strip=True, separator=" ")[:256] + " " + context_before
        
        context_after = ""
        for sibling in img.parent.find_next_siblings(limit=2):
            if not isinstance(sibling, NavigableString):
                context_after += " " + sibling.get_text(strip=True, separator=" ")[:256]

        context_snippet = (context_before + context_after).strip()

        images.append({
            "url": src,
            "alt": alt,
            "header_lineage": header_lineage,
            "context_snippet": context_snippet,
        })
    return images

def get_robot_parser(start_url):
    parsed_uri = urlparse(start_url)
    robots_url = f"{parsed_uri.scheme}://{parsed_uri.netloc}/robots.txt"
    rp = RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.read()
        return rp
    except Exception as e:
        logging.error(f"Error reading robots.txt: {e}")
        return None

def fetch_page(url, user_agent):
    try:
        response = requests.get(url, timeout=10, headers={'User-Agent': user_agent})
        response.raise_for_status()
        if 'text/html' not in response.headers.get('content-type', ''):
            logging.info(f"  -> Skipping non-HTML content at {url}")
            return None
        return response
    except requests.RequestException as e:
        logging.error(f"  -> Failed to fetch {url}: {e}")
        return None

def extract_headings(soup):
    headings = []
    for h in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
        level = int(h.name[1])
        text = h.get_text(strip=True)
        if text:
            headings.append({"level": level, "text": text})
    return headings

def parse_page(soup, url):
    content_container = soup.find('main') or soup.find('article') or soup.body
    if not content_container:
        return None

    for tag in content_container.find_all(is_boilerplate):
        tag.decompose()

    return {
        "url": url,
        "title": soup.title.string.strip() if soup.title else "",
        "clean_text": content_container.get_text(separator='\n', strip=True),
        "images": extract_images(content_container, url),
        "headings": extract_headings(content_container),
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

def discover_links(soup, base_url, domain, same_domain, include, exclude):
    links = []
    for a in soup.find_all('a', href=True):
        link = a['href']
        abs_link = urljoin(base_url, link)
        parsed_link = urlparse(abs_link)

        if (
            parsed_link.scheme in ['http', 'https'] and
            (not same_domain or parsed_link.netloc == domain) and
            (not include or re.search(include, abs_link))
            and
            (not exclude or not re.search(exclude, abs_link))
        ):
            links.append(normalize_url(abs_link))
    return links

def crawl(start_url, out_dir, max_pages, same_domain, include, exclude, delay):
    """
    Crawls a website starting from start_url and saves the content to out_path.
    """
    start_url = normalize_url(start_url)
    parsed_start = urlparse(start_url)
    domain = parsed_start.netloc
    
    # Create output directory
    date_str = time.strftime("%Y-%m-%d")
    output_path = Path(out_dir) / "raw" / f"date={date_str}"
    output_path.mkdir(parents=True, exist_ok=True)
    out_file = output_path / f"{domain}.jsonl"

    robot_parser = get_robot_parser(start_url)
    user_agent = 'UniversityRAGCrawler/1.0'

    q = deque([start_url])
    seen_pages = {start_url}
    pages_crawled = 0

    with open(out_file, 'w') as f:
        while q and pages_crawled < max_pages:
            url = q.popleft()
            
            if robot_parser and not robot_parser.can_fetch(user_agent, url):
                logging.info(f"Skipping {url} due to robots.txt")
                continue

            logging.info(f"[{pages_crawled + 1}/{max_pages}] Crawling: {url}")

            response = fetch_page(url, user_agent)
            if not response:
                continue

            soup = BeautifulSoup(response.text, 'lxml')
            page_data = parse_page(soup, url)

            if page_data:
                f.write(json.dumps(page_data) + '\n')
                pages_crawled += 1

                new_links = discover_links(soup, url, domain, same_domain, include, exclude)
                for link in new_links:
                    if link not in seen_pages:
                        q.append(link)
                        seen_pages.add(link)

            time.sleep(delay)

    logging.info(f"\nFinished crawling. Crawled {pages_crawled} pages.")
    logging.info(f"Output saved to: {out_file}")




if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Crawl a university website for RAG (text + image URLs)")
    ap.add_argument("--start", required=True, help="Start URL, e.g., https://www.university.edu/")
    ap.add_argument("--out-dir", default="data", help="Base directory for output JSONL files")
    ap.add_argument("--max-pages", type=int, default=100, help="Max pages to crawl")
    ap.add_argument("--same-domain", action="store_true", help="Restrict to the same domain only")
    ap.add_argument("--include", help="Only crawl URLs matching this regex")
    ap.add_argument("--exclude", help="Skip URLs matching this regex")
    ap.add_argument("--delay", type=float, default=0.5, help="Delay between requests (seconds)")
    args = ap.parse_args()

    crawl(
        start_url=args.start,
        out_dir=args.out_dir,
        max_pages=args.max_pages,
        same_domain=args.same_domain,
        include=args.include,
        exclude=args.exclude,
        delay=args.delay,
    )
