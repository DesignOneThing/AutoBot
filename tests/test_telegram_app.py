from avtonet_bot.telegram_app import _find_url_arg_index


def test_find_url_arg_index_allows_multi_word_search_names() -> None:
    args = [
        "ALL",
        "CARS",
        "<https://www.avto.net/Ads/results.asp?znamka=&model=>",
        "5",
        "deal=on",
    ]

    assert _find_url_arg_index(args) == 2
