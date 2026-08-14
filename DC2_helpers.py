import logging
import pathlib
import tkinter as tk

def init_logger(script_name):
    
    logging.basicConfig(level = logging.DEBUG)
    logging.getLogger().handlers.clear()
    
    logger = logging.getLogger(script_name)
    
    if not logger.handlers:
        
        # log format
        formatter = logging.Formatter('%(asctime)s - %(name)20s - %(levelname)s - %(message)s')

        # handler for output to log file. This logger is the most verbose logger possible, capturing all debug statements.
        file_handler = logging.FileHandler('DC2.log')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)


        # handler for output to terminal. This logger is verbose if associated with the file the user is running, otherwise it is less verbose.
        terminal_handler = logging.StreamHandler()

        if script_name == '__main__':
            terminal_handler.setLevel(logging.INFO)
        else:
            terminal_handler.setLevel(logging.WARNING)

        terminal_handler.setFormatter(formatter)

        logger.addHandler(terminal_handler)
        logger.addHandler(file_handler)

    # When the user runs a file, this line places a break in the logfile (makes reading the log file easier).
    if script_name == '__main__':
        logger.info('\n\nNew process starting...\n')

    return logger

def select_folder(title='Select Build Folder'):
    
    # setup initial file location
    init_dir = pathlib.Path.home()
    if (init_dir / 'Data').is_dir():
        init_dir /= 'Data'

    root = tk.Tk()
    root.wm_attributes('-topmost', 1)
    root.withdraw()

    path = tk.filedialog.askdirectory(
        title=title,
        initialdir = init_dir,
        parent=root
    )

    return pathlib.Path(path)

class SensorNotConnectedError(Exception):
    """
    Exception raised when a sensor fails initial connection check
    """
    
    def __init__(self, message):
        
        super().__init__(message)
        
        