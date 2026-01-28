import logging
import yt_dlp as youtube_dl
from constants import tr_cli as tr
import variables as var
from media.item import item_builders, item_loaders, item_id_generators
from media.url import URLItem, url_item_id_generator
from media.item import ValidationFailedError
from util import format_time
import os


log = logging.getLogger("bot")


def get_playlist_info(url, start_index=0, user=""):
    ydl_opts = {
        'extract_flat': 'in_playlist',
        'verbose': var.config.getboolean('debug', 'youtube_dl'),
        'js_runtimes': {'node': {}, 'deno': {}},
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android']
            }
        }
    }

    cookie = var.config.get('youtube_dl', 'cookie_file')
    if cookie:
        ydl_opts['cookiefile'] = var.config.get('youtube_dl', 'cookie_file')

    user_agent = var.config.get('youtube_dl', 'user_agent')
    if user_agent:
        youtube_dl.utils.std_headers['User-Agent'] = var.config.get('youtube_dl', 'user_agent')

    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        attempts = var.config.getint('bot', 'download_attempts')
        info = None
        for i in range(attempts):
            try:
                info = ydl.extract_info(url, download=False)
                break
            except Exception as ex:
                log.exception(ex, exc_info=True)
                continue
        
        if not info:
            return

        if 'entries' not in info:
            return

        playlist_title = info.get('title', 'Unknown Playlist')
        entries = info['entries']
        
        max_tracks = var.config.getint('bot', 'max_track_playlist')
        count = 0
        
        try:
            for j, entry in enumerate(entries):
                if j < start_index:
                    continue
                
                if count >= max_tracks:
                    break
                
                # Unknow String if No title into the json
                title = entry.get('title', "Unknown Title")
                # Add youtube url if the url in the json isn't a full url
                if entry.get('url'):
                    item_url = entry['url'] if entry['url'][0:4] == 'http' \
                        else "https://www.youtube.com/watch?v=" + entry['url']
                else:
                    item_url = "" # Should handle missing URL

                duration = entry.get('duration', 0)

                music = {
                    "type": "url_from_playlist",
                    "url": item_url,
                    "title": title,
                    "playlist_url": url,
                    "playlist_title": playlist_title,
                    "user": user,
                    "duration": duration
                }

                yield music
                count += 1
                
        except Exception as ex:
             log.exception(ex, exc_info=True)



def playlist_url_item_builder(**kwargs):
    return PlaylistURLItem(kwargs['url'],
                           kwargs['title'],
                           kwargs['playlist_url'],
                           kwargs['playlist_title'],
                           kwargs.get('duration', 0))


def playlist_url_item_loader(_dict):
    return PlaylistURLItem("", "", "", "", 0, _dict)


item_builders['url_from_playlist'] = playlist_url_item_builder
item_loaders['url_from_playlist'] = playlist_url_item_loader
item_id_generators['url_from_playlist'] = url_item_id_generator


class PlaylistURLItem(URLItem):
    def __init__(self, url, title, playlist_url, playlist_title, duration, from_dict=None):
        if from_dict is None:
            super().__init__(url)
            self.title = title
            self.playlist_url = playlist_url
            self.playlist_title = playlist_title
            self.duration = duration
        else:
            super().__init__("", from_dict)
            self.playlist_title = from_dict['playlist_title']
            self.playlist_url = from_dict['playlist_url']

        self.type = "url_from_playlist"

    def to_dict(self):
        tmp_dict = super().to_dict()
        tmp_dict['playlist_url'] = self.playlist_url
        tmp_dict['playlist_title'] = self.playlist_title

        return tmp_dict

        return "[url] {title} ({url}) from playlist {playlist}".format(
            title=self.title,
            url=self.url,
            playlist=self.playlist_title
        )

    def validate(self):
        try:
            self.validating_lock.acquire()
            if self.ready in ['yes', 'validated']:
                return True

            if os.path.exists(self.path):
                self.ready = "yes"
                return True

            # Check if this url is banned
            if var.db.has_option('url_ban', self.url):
                raise ValidationFailedError(tr('url_ban', url=self.url))

            # We don't fetch info here to avoid mass banning from yt when keeping validation of a playlist.
            # We trust the information from the playlist.
            
            # Check if the song is too long and is not whitelisted
            max_duration = var.config.getint('bot', 'max_track_duration') * 60
            if max_duration and \
                    not var.db.has_option('url_whitelist', self.url) and \
                    self.duration > max_duration:
                log.info(
                    "url: " + self.url + " has a duration of " + str(self.duration / 60) + " min -- too long")
                raise ValidationFailedError(tr('too_long', song=self.format_title(),
                                               duration=format_time(self.duration),
                                               max_duration=format_time(max_duration)))
            else:
                self.ready = "validated"
                self.version += 1  # notify wrapper to save me
                return True
        finally:
            self.validating_lock.release()

    def format_song_string(self, user):
        return tr("url_from_playlist_item",
                  title=self.title,
                  url=self.url,
                  playlist_url=self.playlist_url,
                  playlist=self.playlist_title,
                  user=user)

    def format_current_playing(self, user):
        display = tr("now_playing", item=self.format_song_string(user))

        if self.thumbnail:
            thumbnail_html = '<img width="80" src="data:image/jpge;base64,' + \
                             self.thumbnail + '"/>'
            display += "<br />" + thumbnail_html

        return display

    def display_type(self):
        return tr("url_from_playlist")
