import importlib
import logging
import os
import re

import discord
from discord.ext import commands

from . import waaai
from . import zerobin

log = logging.getLogger(__name__)

PLUGIN_DESC = "__dango_plugin_desc__"


def plugin(depends=None):
    def real_decorator(cls):
        setattr(cls, PLUGIN_DESC, PluginDesc(
            depends=depends or []
        ))
        return cls
    return real_decorator


class PluginDesc:
    def __init__(self, depends):
        self.depends = depends


class DangoContext(commands.Context):

    async def send(self, content=None, *args, **kwargs):
        """Override for send to add message filtering."""
        # TODO - this maybe shouldn't be in dango
        content = re.sub("@everyone", "@\u200beveryone", content, flags=re.IGNORECASE)
        content = re.sub("@here", "@\u200bhere", content, flags=re.IGNORECASE)

        if len(content) > 2000:
            try:
                zbin_url = await zerobin.upload_zerobin(content)
                waaai_url = await waaai.send_to_waaai(
                    zbin_url, self.bot.config.waaai_api_key)  # TODO
                content = "Content too long: %s" % waaai_url
            except:  # TODO
                log.exception("Exception when uploading to zerobin...")
                # text_file = io.BytesIO(content.encode('utf8'))
                content = "Way too big..."

        sent_message = await super().send(content, *args, **kwargs)
        self.bot.dispatch("dango_message_sent", sent_message, self)
        return sent_message


class DangoBotBase(commands.bot.BotBase):

    def __init__(self, *args, config=None, **kwargs):
        self.config = config

        self._dango_unloaded_cogs = {}
        return super().__init__(*args, **kwargs)

    def get_context(self, message):
        return super().get_context(message, cls=DangoContext)

    def add_cog(self, cls):
        """Tries to load a cog.

        If not all dependencies are loaded, will defer until they are.
        """
        desc = getattr(cls, PLUGIN_DESC)
        if not desc:
            raise ValueError("This is not a dango cog.")

        depends = [self.get_cog(name) for name in desc.depends]
        if not all(depends):
            self._dango_unloaded_cogs[cls.__name__] = cls
            return

        cog = cls(*depends)
        super().add_cog(cog)
        log.debug("Loaded dcog %s.%s", cls.__module__, cls.__name__)

        # Try loading previously unloaded plugins.
        unloaded_plugins = self._dango_unloaded_cogs
        self._dango_unloaded_cogs = {}
        for plugin in unloaded_plugins.values():
            self.add_cog(plugin)

    def remove_cog(self, name, remove=True):
        """Unloads a cog.

        Name of a cog must be it's class name.
        If another cog depends on this one, unload but do not remove it.
        """
        cog = self.cogs.get(name, None)

        if remove:
            if name in self._dango_unloaded_cogs:
                del self._dango_unloaded_cogs[name]
        elif cog:
            self._dango_unloaded_cogs[name] = type(cog)

        if not cog:
            return

        if hasattr(cog, PLUGIN_DESC):
            self.unload_cog_deps(cog)

        super().remove_cog(name)
        log.debug("Unloaded dcog %s", name)

    def unload_cog_deps(self, unloading_cog):
        for cog_name, cog_inst in self.cogs.copy().items():
            desc = getattr(cog_inst, PLUGIN_DESC)
            if not desc:
                continue

            if type(unloading_cog).__name__ in desc.depends:
                self.remove_cog(cog_name, remove=False)

    def load_extension(self, name):
        """Override load extension to auto-detect dcogs.

        Note: We do not override unload_extension, as it works fine.
        """
        if name in self.extensions:
            return

        log.info("Loading extension {}".format(name))
        lib = importlib.import_module(name)

        for item in dir(lib):
            val = getattr(lib, item)
            if isinstance(val, type) and hasattr(val, PLUGIN_DESC):
                self.add_cog(val)

        self.extensions[name] = lib

    def watch_plugin_dir(self, dire):
        for item in os.listdir(dire):
            if item.endswith(".py"):
                item = item[:-3]
                if item == "__init__":
                    continue
            elif os.path.isdir(os.path.join(dire, item)):
                if "__init__.py" not in os.listdir(os.path.join(dire, item)):
                    continue
            self.load_extension("{}.{}".format(dire, item))

        if self._dango_unloaded_cogs:
            log.warning(
                "Some plugins were unable to load due to missing deps: %s",
                ",".join("%s.%s" % (c.__module__, c.__name__)
                         for c in self._dango_unloaded_cogs))


class DangoAutoShardedBot(DangoBotBase, discord.AutoShardedClient):
    pass


class DangoBot(DangoBotBase, discord.Client):
    pass