from dataclasses import dataclass, field
# from typing import List

from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from parser2 import mimetype
import time

import httpx
from lxml import etree
import html5_parser
import xxhash
import re

from ebooklib import epub


@dataclass
class Image:
    filehash: str
    filename: str
    content: bytes
    mimetype: str


@dataclass
class Chapter:
    url: str = ""
    title: str = ""
    filename: str = ""
    content: str = ""


@dataclass
class Volume:
    title: str = ""
    filename: str = ""
    content: str = ""
    chapters: list[Chapter] = field(default_factory=list)


def get_with_retry(client: httpx.Client, url: str, retrys: int = 5, sleep_time: float = 2):
    response = None

    for i in range(0, retrys):
        response = client.get(url)
        if response.status_code == httpx.codes.OK:
            break
        else:
            time.sleep(sleep_time)

    if response.status_code == httpx.codes.OK:
        return response
    else:
        print(f"[ERR] get_with_retry - response.status_code != httpx.codes.OK - url:{url}")
        return None


def generate_volume_content(title):
    return (
        f'  <h1 style="text-align: center;">{title}</h1>\n'
    )


DEFAULT_VOLUME_TITILE = "Том 0"
DEFAULT_VOLUME_FILENAME = "volume-0.xhtml"
DEFAULT_VOLUME_CONTENT = generate_volume_content("Том 0")

BASE_URL = "https://tl.rulate.ru"
ENABLE_IMAGES = True


class Book:
    title: str = ""
    description: str = ""
    language: str = "ru"
    volumes: list[Volume] = []
    images: dict = {}
    uid: str = ""
    cover: Image

    def __init__(self, url):
        self.url = str(url)
        self.volumes.append(Volume(DEFAULT_VOLUME_TITILE, DEFAULT_VOLUME_FILENAME, DEFAULT_VOLUME_CONTENT))

    def print_content(self):
        print(self.title)
        for vol in self.volumes:
            print(f"├── {vol.title:<96}    ({vol.filename})")
            for ch in vol.chapters:
                print(f"│   ├── {ch.title:<90}    ({ch.filename})")

    def download_image(self, url) -> Image:
        with httpx.Client(timeout=10, http2=True, follow_redirects=True) as client:
            response = get_with_retry(client, url)
            if response:
                raw = response.content
                img_ext, img_mime = mimetype.get_file_extension(raw)
                if img_ext:
                    img_hash = xxhash.xxh3_128_hexdigest(raw)
                    return Image(filehash=img_hash, filename=f"{img_hash}{img_ext}", content=raw, mimetype=img_mime)
                else:
                    print(f"[ERR] Book.download_image - Invalid file extension. url: {url}")
                    return None

    def img_work(self, img):
        if img is None:
            return

        img_src = img.get('src')

        if not img_src:
            return

        img_url = img_src

        if img_src[0:1] == '/':
            img_url = BASE_URL + img_src

        image = self.download_image(img_url)

        if not image:
            img.getparent().remove(img)
            return

        self.images[image.filehash] = image

        img.set("src", f"../Images/{image.filename}")
        img.set("alt", f"x{image.filename}")
        img.set("style", "display:block;margin-left:auto;margin-right:auto;")

    def parse_chapter(self, chapter: Chapter) -> Chapter:
        with httpx.Client(timeout=10) as client:
            new_ch = chapter
            response = get_with_retry(client, new_ch.url)

            if response:
                root = html5_parser.parse(response.content)
                content_text = root.xpath('//*[@class="content-text"]')[0]

                if ENABLE_IMAGES:
                    with ThreadPoolExecutor(max_workers=4) as pool:
                        images = content_text.xpath('.//img')
                        pool.map(self.img_work, images)

                # cleanup
                for p in content_text.xpath('.//p'):
                    if len(p) == 0:
                        if p.text is not None:
                            if p.text == '':
                                p.getparent().remove(p)
                        else:
                            p.getparent().remove(p)

                for i in content_text.xpath('.//*'):
                    style = i.get("style")
                    if style is not None:
                        style = re.sub(R'margin-left:[\s]*0cm[;]*',     R'', style)
                        style = re.sub(R'margin-right:[\s]*0cm[;]*',    R'', style)
                        style = re.sub(R'font-size:[\s]*[\d]*px[;]*',   R'', style)
                        i.set("style", style)

                xml_body = etree.Element("div")
                xml_body.append(etree.fromstring("<h2>{}</h2>".format(new_ch.title)))
                xml_body.append(content_text)

                etree.indent(xml_body, space="\t")

                new_ch.content = etree.tostring(
                    xml_body,
                    # doctype="<!DOCTYPE html>",
                    encoding="UTF-8",
                    method="xml",
                    pretty_print=True,
                    with_tail=False,
                    # xml_declaration=True,
                )

            print(f"[INF] Book.parse_chapter - completed - filename: {new_ch.filename}")
            return new_ch

    def parse(self):
        with httpx.Client(timeout=10) as client:
            response = get_with_retry(client, self.url)
            if response:
                root = html5_parser.parse(response.content)
                # print(etree.tostring(root, pretty_print=True, encoding="unicode"))

                self.uid = 'idtlrulate' + self.url.split('/')[-1:][0]
                self.title = root.xpath("/html/body/div[2]/div[3]/div[1]/h1")[0].text.split(" / ")[-1:][0]
                self.description = ''.join(root.xpath("/html/body/div[2]/div[3]/div[1]/div[1]/div[3]")[0].itertext())

                cover_url = root.xpath('//*[@class="slick"]/div/img')[0].get("src")
                if cover_url[0:1] == '/':
                    cover_url = BASE_URL + cover_url
                self.cover = self.download_image(cover_url)

                table = root.xpath("/html/body/div[2]/div[3]/div[1]/form/table/tbody/tr")

                vol_i = 0
                for row in table:
                    if row.get("id"):
                        # print(etree.tostring(row, pretty_print=True, encoding="unicode"))
                        if row.get("id")[0:3] == "vol":
                            vol_i += 1
                            voltitle = row.xpath("td/strong")[0].text

                            self.volumes += [Volume(voltitle, f"volume-{vol_i}.xhtml", generate_volume_content(voltitle))]

                        elif row.get("id")[0:1] == "c":
                            a = row.xpath("td/a")
                            if len(a) > 1:
                                curl = BASE_URL + a[0].get("href")
                                ctitle = a[0].text
                                ctitle = re.sub(R'[\s]*(.*)', R'\1', ctitle)
                                ctitle = re.sub(R'[\s]{2,}',  R' ',  ctitle)
                                cid = row.get("id").split("_")[1]

                                self.volumes[-1:][0].chapters += [Chapter(curl, ctitle, f"chapter-{cid}.xhtml")]

    def replace_chapter(self, vol_i, ch_i, ch):
        self.volumes[vol_i].chapters[ch_i] = ch

    def parse_chapters(self):
        with ProcessPoolExecutor(max_workers=8) as pool:
            for vol_i in range(0, len(self.volumes)):
                for ch_i in range(0, len(self.volumes[vol_i].chapters)):
                    pool.submit(self.replace_chapter, vol_i, ch_i, self.parse_chapter(self.volumes[vol_i].chapters[ch_i]))

    def save_as_epub(self, outfilename):
        ebook = epub.EpubBook()

        ebook.set_identifier(self.uid)
        ebook.set_title(self.title)
        ebook.set_language(self.language)
        ebook.add_metadata('DC', 'description', self.description)

        ebook.spine.append("nav")

        ebook.set_cover(file_name=f"Images/{self.cover.filename}", content=self.cover.content)

        ebook.toc = []

        for vol in self.volumes:
            if len(vol.chapters) > 0:
                bookvol = epub.EpubHtml(title=vol.title, file_name=f"Text/{vol.filename}", content=vol.content)
                ebook.add_item(bookvol)
                ebook.spine.append(bookvol)

                bookchs = []

                for ch in vol.chapters:
                    bookch = epub.EpubHtml(title=ch.title, file_name=f"Text/{ch.filename}", content=ch.content)
                    ebook.add_item(bookch)
                    ebook.spine.append(bookch)

                    bookchs.append(bookch)

                ebook.toc.append([bookvol, bookchs])

        for key, image in self.images.items():
            bookimg = epub.EpubImage(
                uid=f"x{image.filehash}",
                file_name=f"Images/{image.filename}",
                media_type=image.mimetype,
                content=image.content,
            )
            ebook.add_item(bookimg)

        ebook.add_item(epub.EpubNcx())
        ebook.add_item(epub.EpubNav())

        epub.write_epub(outfilename, ebook, {})
