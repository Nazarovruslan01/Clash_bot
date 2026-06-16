import configs
import utils
from log import setup_logging
from utils import *
from coc_bot import CoC_Bot

if __name__ == "__main__":
    args = parse_args(debug=True, id="main")
    init_instance(args.id)
    setup_logging(args.id, configs.DEBUG)
    bot = CoC_Bot()
    # TODO: Add test cases here