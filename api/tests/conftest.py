"""
Pytest conftest.py - Proje kök dizinini sys.path'e ekler.
Bu sayede `scripts.*` ve `api.*` modülleri tüm test dosyalarından import edilebilir.
"""
import sys
import os

# Proje kök dizini sys.path'e ekle
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
