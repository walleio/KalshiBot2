import torch.nn as nn
import torch
import process_data as ld
from torch.utils.data import DataLoader
from tqdm import tqdm
import matplotlib.pyplot as plt

# define the model
class KalshiCNN(nn.Module):
    def __init__(self, seq_len):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv1d(in_channels=2, out_channels=32, kernel_size=5, padding=2),
            nn.ReLU(),
            nn.Conv1d(32, 64, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.AdaptiveAvgPool1d(1)
        )
        self.regressor = nn.Sequential(
            nn.Flatten(),
            nn.Linear(64, 50),
            nn.ReLU(),
            nn.Linear(50, 1)
        )

    def forward(self, x):      
        x = self.features(x)
        return self.regressor(x)

train_ds = ld.KalshiDataset()
train_dl = DataLoader(train_ds, batch_size=32, shuffle=True)

model = KalshiCNN(train_ds.seq_len)
loss_fn   = nn.MSELoss()
optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)

if __name__ == "__main__":
    losses = []
    # train the model
    for epoch in tqdm(range(400)):
        model.train()
        for batch, label in train_dl:
            pred = model(batch).squeeze(1)
            loss = loss_fn(pred, label.squeeze(1))
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
    
        losses.append(loss.item())

    torch.save(model, 'model.pth')

    # uncomment to see learning ability
    '''
    plt.plot(range(400), losses)
    plt.xlabel('Epochs')
    plt.ylabel('Loss')
    plt.title('Loss vs Epochs')
    plt.show()
    '''