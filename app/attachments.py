"""Owner-scoped image messages. Decode, bound and re-encode before storage."""
import base64
import hashlib
import io
import sqlite3
import warnings
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps
from app.agent import AgentError


class ImageStore:
    def __init__(self, directory):
        self.directory=Path(directory)
        self.directory.mkdir(parents=True,exist_ok=True)
        self.directory.chmod(0o700)
        self.path=self.directory/'images.sqlite3'
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS images (id TEXT PRIMARY KEY, owner TEXT, path TEXT)')
        self.path.chmod(0o600)

    def save(self,owner,data_url):
        try:
            header,encoded=data_url.split(',',1)
            if header not in {'data:image/jpeg;base64','data:image/png;base64','data:image/webp;base64'}:
                raise ValueError()
            raw=base64.b64decode(encoded,validate=True)
            if not raw or len(raw)>8_000_000:
                raise ValueError()
            with warnings.catch_warnings():
                warnings.simplefilter('error',Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(raw)) as source:
                    if source.format not in {'JPEG','PNG','WEBP'} or source.width*source.height>24_000_000:
                        raise ValueError()
                    source.load()
                    image=ImageOps.exif_transpose(source).convert('RGB')
                    image.thumbnail((1600,1600))
                    output=io.BytesIO()
                    image.save(output,format='JPEG',quality=90)
        except Exception:
            raise AgentError('图片无法读取，请选择 8 MB 以内的 JPG、PNG 或 WebP 图片。',400) from None
        mid=uuid4().hex
        folder=self.directory/hashlib.sha256(owner.encode()).hexdigest()[:32]
        folder.mkdir(exist_ok=True);folder.chmod(0o700)
        path=folder/(mid+'.jpg')
        path.write_bytes(output.getvalue());path.chmod(0o600)
        with sqlite3.connect(self.path) as db:
            db.execute('INSERT INTO images VALUES (?,?,?)',(mid,owner,str(path)))
        return {'id':mid,'url':f'/api/contact/images/{mid}'}

    def resolve(self,owner,mid):
        with sqlite3.connect(self.path) as db:
            row=db.execute('SELECT path FROM images WHERE id=? AND owner=?',(mid,owner)).fetchone()
        if not row or not Path(row[0]).is_file():
            raise AgentError('找不到属于当前会话的图片。',404)
        return row[0]
