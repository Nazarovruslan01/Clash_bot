def launch_proc(id, gui_server_port=None):
    import configs
    import utils
    from log import setup_logging
    from coc_bot import CoC_Bot

    if gui_server_port is not None:
        utils.GUI_SERVER_PORT = gui_server_port
    utils.init_instance(id)
    setup_logging(id, configs.DEBUG)
    bot = CoC_Bot()
    bot.run()

def cmd_launch(args):
    import configs
    import utils
    if configs.DISABLE_DEVICE_SLEEP: utils.disable_sleep()
    launch_proc(args.id)

def gui_launch(args):
    from multiprocessing import Process
    import configs
    import utils
    from gui import init_gui, get_gui
    
    procs = {}
    pipe = init_gui(args.id)
    
    if configs.DISABLE_DEVICE_SLEEP: Process(target=utils.disable_sleep).start()
    
    server_port = get_gui().server_port

    if args.id is not None:
        p = Process(target=launch_proc, args=(args.id, server_port))
        p.start()
        procs[args.id] = p
    try:
        while True:
            if not pipe.poll(1.0):
                continue
            data = pipe.recv()
            if data == -1: raise SystemExit
            action, id = data.get("action"), data.get("id")
            if action == "start":
                p = Process(target=launch_proc, args=(data.get("id"), server_port))
                p.start()
                procs[id] = p
            elif action == "stop":
                p = procs.pop(id, None)
                if p and p.is_alive():
                    p.terminate()
                    p.join()
    except (EOFError, KeyboardInterrupt, SystemExit):
        get_gui().stop()
        pipe.close()
        for p in procs.values():
            if p and p.is_alive():
                p.terminate()
                p.join()

def launch():
    import utils
    args = utils.parse_args()
    if args.gui: gui_launch(args)
    else: cmd_launch(args)
