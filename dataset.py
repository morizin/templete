import os 
import cv2
import numpy as np 
import skimage.io
import torch 
from torch.utils.data import Dataset 
import config 
import albumentations
from tqdm import tqdm 
import time 
from templete.preprocess import crop_white

class PANDADataset(Dataset):
    def __init__(self,
                 image_folder,   
                 df,
                 image_size,
                 num_tiles,
                 rand=False,
                 transform=None,
                 attention_df=None
                ):
        self.image_folder = image_folder
        self.df = df.reset_index(drop=True)
        self.image_size = image_size
        self.num_tiles = num_tiles
        self.rand = rand
        self.transform = transform
        self.atten_df = attention_df

    def __len__(self):
        return self.df.shape[0]

    def __getitem__(self, index):
        row = self.df.iloc[index]
        img_id = row.image_id
        if config.tile_png:
            if config.use_attention:
                subdf=self.atten_df[self.atten_df.image_id==img_id].sort_values(
                    by=[f'attention_fold_{config.fold}'],
                    ascending=False)
                file_list = subdf.file_name.values[:self.num_tiles]
                file_list = [fn.split('_')[-1] for fn in file_list]
            else:
                file_list = [str(i)+'.jpg' for i in range(self.num_tiles)]
            img_tiles = []
            for fn in file_list:
                tile_path = os.path.join(self.image_folder,img_id,fn)
                tile = skimage.io.imread(tile_path)
                img_tiles.append(tile)
        else:
            if config.tiff:
                # tiff_file = os.path.join(self.image_folder, f'{img_id}.tiff')
                # image = skimage.io.MultiImage(tiff_file)[1]
                pass
            else:
                img_file = os.path.join(self.image_folder,f'{img_id}.jpg')
                image = cv2.imread(img_file)
                image = cv2.cvtColor(image,cv2.COLOR_BGR2RGB)
                
            if config.crop_white:
                image = crop_white(image)

            if config.BRS:  
                img_tiles = get_tiles_brs(image,self.image_size,self.num_tiles)
            else:
                img_tiles = get_tiles(image,self.image_size,self.num_tiles)

        if self.rand:
            idxes = np.random.choice(list(range(self.num_tiles)), self.num_tiles, replace=False)
        else:
            idxes = list(range(self.num_tiles))

        n_row_tiles = int(np.sqrt(self.num_tiles))
        images = np.zeros((self.image_size * n_row_tiles, self.image_size * n_row_tiles, 3))
        for h in range(n_row_tiles):
            for w in range(n_row_tiles):
                i = h * n_row_tiles + w
    
                if len(img_tiles) > idxes[i]:
                    this_img = img_tiles[idxes[i]]
                else:
                    this_img = np.ones((self.image_size, self.image_size, 3)).astype(np.uint8) * 255
                this_img = 255 - this_img
                if self.transform is not None:
                    this_img = self.transform(image=this_img)['image']
                h1 = h * self.image_size
                w1 = w * self.image_size
                images[h1:h1+self.image_size, w1:w1+self.image_size] = this_img

        if self.transform is not None:
            images = self.transform(image=images)['image']
        images = images.astype(np.float32)
        images /= 255
        images = images.transpose(2, 0, 1)

        if config.model_type=='ord_reg':
            label = np.zeros(5).astype(np.float32)
            label[:row.isup_grade] = 1.
        elif config.model_type=='reg':
            label = row.isup_grade
            label = torch.tensor(label).float()
        else:
            label = raw.isup_grade
            label = torch.tensor(label).long()

        return torch.tensor(images).float(),label


class  PANDADatasetTiles(Dataset):
    def __init__(self,image_folder,df,image_size,num_tiles,transform=None,attention_df=None):
        self.image_folder = image_folder
        self.df = df.reset_index(drop=True)
        self.image_size = image_size 
        self.num_tiles = num_tiles
        self.transform = transform
        self.atten_df = attention_df
        
    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        row = self.df.iloc[idx]
        img_id = row.image_id
        if config.tile_png:
            if config.use_attention:
                subdf=self.atten_df[self.atten_df.image_id==img_id].sort_values(
                    by=[f'attention_fold_{config.fold}'],
                    ascending=False)
                file_list = subdf.file_name.values[:self.num_tiles]
                file_list = [fn.split('_')[-1] for fn in file_list]
            else:
                file_list = [str(i)+'.jpg' for i in range(self.num_tiles)]
            img_tiles = []
            for fn in file_list:
                tile_path = os.path.join(self.image_folder,img_id,fn)
                tile = skimage.io.imread(tile_path)
                img_tiles.append(tile)
        else:
            if config.tiff:
                tiff_file = os.path.join(self.image_folder, f'{img_id}.tiff')
                image = skimage.io.MultiImage(tiff_file)[1]
            else:
                img_file = os.path.join(self.image_folder,f'{img_id}.jpg')
                image = cv2.imread(img_file)
                image = cv2.cvtColor(image,cv2.COLOR_BGR2RGB)
                
            if config.crop_white:
                image = crop_white(image)

            if config.BRS:  
                img_tiles = get_tiles_brs(image,self.image_size,self.num_tiles)
            else:
                img_tiles = get_tiles(image,self.image_size,self.num_tiles)

        images = np.zeros((self.num_tiles,3,self.image_size,self.image_size),np.float32)
        for i,tile in enumerate(img_tiles):
            if self.transform:
                tile = self.transform(image=tile)['image']
            tile = tile.astype(np.float32)
            tile /=255. 
            tile = tile.transpose(2,0,1)
            images[i,:,:,:] = tile 

        if config.model_type=='ord_reg':
            label = np.zeros(5).astype(np.float32)
            label[:row.isup_grade] = 1.
        elif config.model_type=='reg':
            label = row.isup_grade
            label = torch.tensor(label).float()
        else:
            label = row.isup_grade
            label = torch.tensor(label).long()

        return torch.tensor(images).float(),label 


def blue_ratio_selection(img):
    hue = (100.*img[:,:,2])/(1.+img[:,:,0]+img[:,:,1])
    intensity = 256./(1.+img[:,:,0]+img[:,:,1]+img[:,:,2])
    blue_ratio = hue*intensity
    return blue_ratio


def get_tiles(img,sz,num_tiles):
    shape = img.shape
    pad0,pad1 = (sz - shape[0]%sz)%sz, (sz - shape[1]%sz)%sz
    img = np.pad(img,[[pad0//2,pad0-pad0//2],[pad1//2,pad1-pad1//2],[0,0]],
                constant_values=255)
    img = img.reshape(img.shape[0]//sz,sz,img.shape[1]//sz,sz,3)
    img = img.transpose(0,2,1,3,4).reshape(-1,sz,sz,3)
    if len(img) < num_tiles:
        img = np.pad(img,[[0,num_tiles-len(img)],[0,0],[0,0],[0,0]],constant_values=255)
    idxs = np.argsort(img.reshape(img.shape[0],-1).sum(-1))[:num_tiles]
    img = img[idxs]
    return img


def get_tiles_brs(img,sz,num_tiles):
    shape = img.shape
    pad0,pad1 = (sz - shape[0]%sz)%sz, (sz - shape[1]%sz)%sz
    img = np.pad(img,[[pad0//2,pad0-pad0//2],[pad1//2,pad1-pad1//2],[0,0]],
                constant_values=255)
    img = img.reshape(img.shape[0]//sz,sz,img.shape[1]//sz,sz,3)
    img = img.transpose(0,2,1,3,4).reshape(-1,sz,sz,3)
    if len(img) < num_tiles:
        img = np.pad(img,[[0,num_tiles-len(img)],[0,0],[0,0],[0,0]],constant_values=255)
    idxs = np.argsort(img.reshape(img.shape[0],-1).sum(-1))[:num_tiles*4]
    img = img[idxs]
    idxs = np.argsort([blue_ratio_selection(x).sum() for x in img])[::-1][:num_tiles]
    img = img[idxs]
    return img


def get_transforms(phase):
    if phase=='train':
        transform = albumentations.Compose([
            albumentations.Transpose(p=0.5),
            albumentations.VerticalFlip(p=0.5),
            albumentations.HorizontalFlip(p=0.5),
        ])
    else:
        transform = None
    return transform


if __name__=='__main__':
    pass