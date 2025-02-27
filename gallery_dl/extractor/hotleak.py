# -*- coding: utf-8 -*-

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Extractors for https://hotleak.vip/"""

from .common import Extractor, Message
from .. import text, exception

BASE_PATTERN = r"(?:https?://)?(?:www\.)?hotleak\.vip"


class HotleakExtractor(Extractor):
    """Base class for hotleak extractors"""
    category = "hotleak"
    directory_fmt = ("{category}", "{creator}",)
    filename_fmt = "{creator}_{id}.{extension}"
    archive_fmt = "{type}_{creator}_{id}"
    root = "https://hotleak.vip"

    def __init__(self, match):
        Extractor.__init__(self, match)
        self.session.headers["Referer"] = self.root

    def items(self):
        for post in self.posts():
            yield Message.Directory, post
            yield Message.Url, post["url"], post

    def posts(self):
        """Return an iterable containing relevant posts"""
        return ()

    def _pagination(self, url, params):
        params = text.parse_query(params)
        params["page"] = text.parse_int(params.get("page"), 1)

        while True:
            page = self.request(url, params=params).text
            if "</article>" not in page:
                return

            for item in text.extract_iter(
                    page, '<article class="movie-item', '</article>'):
                yield text.extract(item, '<a href="', '"')[0]

            params["page"] += 1


class HotleakPostExtractor(HotleakExtractor):
    """Extractor for individual posts on hotleak"""
    subcategory = "post"
    pattern = (BASE_PATTERN + r"/(?!hot|creators|videos|photos)"
               r"([^/]+)/(photo|video)/(\d+)")
    test = (
        ("https://hotleak.vip/kaiyakawaii/photo/1617145", {
            "pattern": r"https://hotleak\.vip/storage/images/3625"
                       r"/1617145/fefdd5988dfcf6b98cc9e11616018868\.jpg",
            "keyword": {
                "id": 1617145,
                "creator": "kaiyakawaii",
                "type": "photo",
                "filename": "fefdd5988dfcf6b98cc9e11616018868",
                "extension": "jpg",
            },
        }),
        ("https://hotleak.vip/lilmochidoll/video/1625538", {
            "pattern": r"ytdl:https://cdn8-leak\.camhdxx\.com"
                       r"/1661/1625538/index\.m3u8",
            "keyword": {
                "id": 1625538,
                "creator": "lilmochidoll",
                "type": "video",
                "filename": "index",
                "extension": "mp4",
            },
        }),
    )

    def __init__(self, match):
        HotleakExtractor.__init__(self, match)
        self.creator, self.type, self.id = match.groups()

    def posts(self):
        url = "{}/{}/{}/{}".format(
            self.root, self.creator, self.type, self.id)
        page = self.request(url).text
        page = text.extract(
            page, '<div class="movie-image thumb">', '</article>')[0]
        data = {
            "id"     : text.parse_int(self.id),
            "creator": self.creator,
            "type"   : self.type,
        }

        if self.type == "photo":
            data["url"] = text.extract(page, 'data-src="', '"')[0]
            text.nameext_from_url(data["url"], data)

        elif self.type == "video":
            data["url"] = "ytdl:" + text.extract(
                text.unescape(page), '"src":"', '"')[0]
            text.nameext_from_url(data["url"], data)
            data["extension"] = "mp4"

        return (data,)


class HotleakCreatorExtractor(HotleakExtractor):
    """Extractor for all posts from a hotleak creator"""
    subcategory = "creator"
    pattern = BASE_PATTERN + r"/(?!hot|creators|videos|photos)([^/?#]+)/?$"
    test = (
        ("https://hotleak.vip/kaiyakawaii", {
            "range": "1-200",
            "count": 200,
        }),
        ("https://hotleak.vip/stellaviolet", {
            "count": "> 600"
        }),
        ("https://hotleak.vip/doesnotexist", {
            "exception": exception.NotFoundError,
        }),
    )

    def __init__(self, match):
        HotleakExtractor.__init__(self, match)
        self.creator = match.group(1)

    def posts(self):
        url = "{}/{}".format(self.root, self.creator)
        return self._pagination(url)

    def _pagination(self, url):
        headers = {"X-Requested-With": "XMLHttpRequest"}
        params = {"page": 1}

        while True:
            try:
                response = self.request(
                    url, headers=headers, params=params, notfound="creator")
            except exception.HttpError as exc:
                if exc.response.status_code == 429:
                    self.wait(
                        until=exc.response.headers.get("X-RateLimit-Reset"))
                    continue

            posts = response.json()
            if not posts:
                return

            data = {"creator": self.creator}
            for post in posts:
                data["id"] = text.parse_int(post["id"])

                if post["type"] == 0:
                    data["type"] = "photo"
                    data["url"] = self.root + "/storage/" + post["image"]
                    text.nameext_from_url(data["url"], data)

                elif post["type"] == 1:
                    data["type"] = "video"
                    data["url"] = "ytdl:" + post["stream_url_play"]
                    text.nameext_from_url(data["url"], data)
                    data["extension"] = "mp4"

                yield data
            params["page"] += 1


class HotleakCategoryExtractor(HotleakExtractor):
    """Extractor for hotleak categories"""
    subcategory = "category"
    pattern = BASE_PATTERN + r"/(hot|creators|videos|photos)(?:/?\?([^#]+))?"
    test = (
        ("https://hotleak.vip/photos", {
            "pattern": HotleakPostExtractor.pattern,
            "range": "1-50",
            "count": 50,
        }),
        ("https://hotleak.vip/videos"),
        ("https://hotleak.vip/creators", {
            "pattern": HotleakCreatorExtractor.pattern,
            "range": "1-50",
            "count": 50,
        }),
        ("https://hotleak.vip/hot"),
    )

    def __init__(self, match):
        HotleakExtractor.__init__(self, match)
        self._category, self.params = match.groups()

    def items(self):
        url = "{}/{}".format(self.root, self._category)

        if self._category in ("hot", "creators"):
            data = {"_extractor": HotleakCreatorExtractor}
        elif self._category in ("videos", "photos"):
            data = {"_extractor": HotleakPostExtractor}

        for item in self._pagination(url, self.params):
            yield Message.Queue, item, data


class HotleakSearchExtractor(HotleakExtractor):
    """Extractor for hotleak search results"""
    subcategory = "search"
    pattern = BASE_PATTERN + r"/search(?:/?\?([^#]+))"
    test = (
        ("https://hotleak.vip/search?search=gallery-dl", {
            "count": 0,
        }),
        ("https://hotleak.vip/search?search=hannah", {
            "count": "> 30",
        }),
    )

    def __init__(self, match):
        HotleakExtractor.__init__(self, match)
        self.params = match.group(1)

    def items(self):
        data = {"_extractor": HotleakCreatorExtractor}
        for creator in self._pagination(self.root + "/search", self.params):
            yield Message.Queue, creator, data
