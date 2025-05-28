import torch
from torch.utils.data import Dataset
import pandas as pd
import json
import ast

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
import requests
import datetime

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.exceptions import InvalidSignature

class KalshiDataset(Dataset):
    def __init__(self):
        self.data_df = pd.read_csv('data.csv')
        self.label_df = pd.read_csv('labels.csv')
        self.seq_len = self.data_df['dict'].map(lambda s: len(ast.literal_eval(s))).max()

    def __len__(self):
        return len(self.label_df)

    @staticmethod
    def _parse_dict(s):
        out = []
        for d in ast.literal_eval(s):
            out.extend([d['yes_bid']['close']])
        return out

    def __getitem__(self, idx):
        # pad the data to the correct length using 0.0
        numeric = self._parse_dict(self.data_df.iloc[idx]['dict'])
        pad_needed = (self.seq_len*2 - len(numeric))
        numeric.extend([0.0]*pad_needed)
        x = torch.tensor(numeric, dtype=torch.float32).view(2, self.seq_len)

        # get the labels for the data
        lbl_dict = ast.literal_eval(self.label_df.iloc[idx]['dict'])
        y = torch.tensor([lbl_dict['yes_bid']['close']], dtype=torch.float32)

        return x, y

data = KalshiDataset()