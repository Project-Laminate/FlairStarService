from abc import ABC, abstractmethod
import logging

class BaseProcessor(ABC):
    """Base class for all processors"""
    
    def __init__(self, output_dir):
        self.output_dir = output_dir
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    def process(self, *args, **kwargs):
        """Abstract method that all processors must implement"""
        pass 