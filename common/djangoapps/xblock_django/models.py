"""
Models.
"""
from django.utils.translation import ugettext_lazy as _

from django.conf import settings

from django.db.models import TextField

from config_models.models import ConfigurationModel


class XBlockDisableConfig(ConfigurationModel):
    """
    Configuration for disabling and deprecated XBlocks.
    """

    class Meta(ConfigurationModel.Meta):
        app_label = 'xblock_django'

    disabled_blocks = TextField(
        default='', blank=True,
        help_text=_('Space-separated list of XBlocks which should not render.')
    )

    deprecated_blocks = TextField(
        default='', blank=True,
        help_text=_(
            "Adding components in this list will disable the creation of new problem for "
            "those components in Studio. Existing problems will work fine and one can edit "
            "them in Studio."
        )
    )

    @classmethod
    def is_block_type_disabled(cls, block_type):
        """ Return True if block_type is disabled. """

        config = cls.current()
        if not config.enabled:
            return False

        return block_type in config.disabled_blocks.split()

    @classmethod
    def disabled_block_types(cls):
        """ Return list of disabled xblock types. """

        config = cls.current()
        if not config.enabled:
            return ()

        return config.disabled_blocks.split()

    @classmethod
    def deprecated_block_types(cls):
        """ Return list of deprecated xblock types. Merges result from admin settings and settings file """

        config = cls.current()
        deprecated_xblock_types = config.deprecated_blocks.split() if config.enabled else []

        # Merge settings list with one in the admin config;
        if hasattr(settings, 'DEPRECATED_ADVANCED_COMPONENT_TYPES'):
            deprecated_xblock_types.extend(
                c_type for c_type in settings.DEPRECATED_ADVANCED_COMPONENT_TYPES
                if c_type not in deprecated_xblock_types
            )

        return deprecated_xblock_types

    @classmethod
    def __unicode__(cls):
        config = cls.current()
        return u"Disabled xblocks = {disabled_xblocks}\nDeprecated xblocks = {deprecated_xblocks}".format(
            disabled_xblocks=config.disabled_blocks,
            deprecated_xblocks=config.deprecated_blocks
        )
