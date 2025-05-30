import pytest
from unittest.mock import MagicMock, patch
from src.cogs.start import Start

@pytest.fixture
def mock_config_manager():
    mock = MagicMock()
    mock.get_config.side_effect = lambda key: {
        'game_settings': {'starting_level': 1, 'starting_gold': 100},
        'esprits': {'e1': {'esprit_id': 'e1', 'rarity': 'Common'}}
    }[key]
    return mock

@pytest.fixture
def mock_image_generator():
    return MagicMock()

@patch('src.cogs.start.ConfigManager')
@patch('src.cogs.start.ImageGenerator')
def test_init_sets_attributes(mock_image_gen_cls, mock_config_mgr_cls, mock_config_manager, mock_image_generator):
    # Arrange
    mock_config_mgr_cls.return_value = mock_config_manager
    mock_image_gen_cls.return_value = mock_image_generator
    mock_bot = MagicMock()

    # Act
    cog = Start(mock_bot)

    # Assert
    assert cog.bot is mock_bot
    assert cog.config_manager is mock_config_manager
    assert cog.image_generator is mock_image_generator
    assert cog.game_settings == {'starting_level': 1, 'starting_gold': 100}
    assert cog.esprits_data == {'e1': {'esprit_id': 'e1', 'rarity': 'Common'}}
    assert cog.starter_esprit_id is None