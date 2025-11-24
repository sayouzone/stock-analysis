import logging
import os
from time import gmtime, strftime

from __init__ import LOGGING_DIR


class Logger:
    """
    Creates and initializes a logger using the 'logging' Python module.
    """

    def __init__(self, name: str, filename: str = ".log") -> None:
        """
        Initializes a logger.

        Args:
            name (str): The name of the logger.
            filename (str): The base name of the log file.
                Example: "download.filings_2025_11_24_09_35_30_.log" and "ExtractItems_2025_11_24_09_35_30_.log"
        """
        self.timestamp = strftime("%Y_%m_%d_%H_%M_%S", gmtime())
        self.filename = f"{name}_{self.timestamp}_{filename}"
        self.name = name

        # Ensure the logging directory exists
        os.makedirs(LOGGING_DIR, exist_ok=True)

        # Configure what is getting logged to the *.log file
        # We want to capture everything (i.e., DEBUG, INFO, WARNING, ERROR, CRITICAL messages)
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(arctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M",
            filename=os.path.join(LOGGING_DIR, self.filename),
            filemode="a",
        )

        # Define a Handler which writes INFO messages or higher to the sys.stderr (console)
        console = logging.StreamHandler()
        console.setLevel(
            logging.INFO
        )  # This logs INFO, WARNING, ERROR, CRITICAL messages to the console.

        # Set a formatter which is simpler for console use
        formatter = logging.Formatter("%(message)s")

        # Tell the handler to use the formatter
        console.setFormatter(formatter)

        # Add the handler to the root logger
        logging.getLogger("").addHandler(console)

        self.logger_object = logging.getLogger(self.name)

    def get_logger(self) -> logging.Logger:
        """
        Returns the logger object.

        Returns:
            logging.Logger: The logger object.
        """
        return self.logger_object
