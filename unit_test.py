import unittest
from utils import *
import json

with open('auction_result_ex.json', 'r') as json_file:
    json_dict = json.load(json_file)
get_valid_option_test1 = json_dict["Items"][0]

class TestCalculator(unittest.TestCase):

    def test_get_valid_option(self):
        self.assertEqual(
            get_valid_option(get_valid_option_test1), 
            {
                "공격력 ": 3,
                "remain_num": 0,
                "quality": 90,
                "trade_allow_count": 1,
            }
        )


if __name__ == "__main__":
    unittest.main()
