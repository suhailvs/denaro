denaro
======

## Setup with Docker
+ Build the base image with `make build`
+ `$ docker-compose up -d`

## Setup without Docker

#### Optional:
Before installing denaro, you need to create the postgresql database.  
You can find the schema in [schema.sql](schema.sql).  
You have to set environmental variables for database access:
- `DENARO_DATABASE_USER`, default to `denaro`.  
- `DENARO_DATABASE_PASSWORD`, default to an empty string.  
- `DENARO_DATABASE_NAME`, default to `denaro`.  
- `DENARO_DATABASE_HOST`, default to `127.0.0.1`.  

#### Installation:

```bash
# create databsase
createdb denaro2 -U postgres
git clone https://github.com/denaro-coin/denaro
cd denaro
psql -d denaro2 -f schema.sql -U postgres
sudo apt-get install python3-dev libgmp3-dev
pip3 install -r requirements.txt
uvicorn denaro.node.main:app --port 3002
```

Mine a coin:

```bash
python denaro/wallet/wallet.py createwallet
python miner.py DX9n7N3t3yBqdixnYHK4td6CPPcH3D8zsVcF6FQtvdQ6b
python denaro/wallet/wallet.py send -to DYAYzytb555iszf7CryahqtSNwVNkyzSFaRSXYBXJzzsT -d 10
python denaro/wallet/wallet.py balance
```

See on explorer:

```bash
cd explorer
python3 -m http.server 
```

Now visit: http://localhost:8000/

clone the same repo again and replace `denaro2` with `denaro1` and port `3002` with `3001`

Node should now sync the blockchain and start working

## Deployment

https://stackoverflow.com/a/68184694/2351696

```bash
pip install gunicorn
gunicorn denaro.node.main:app -w 1 --timeout 150 -k uvicorn.workers.UvicornWorker -b 127.0.0.1:3002 --daemon

sudo a2enmod proxy_http
<VirtualHost *:80>
    ServerName denaro-node.stackschools.com
    ProxyPreserveHost On
    ProxyPass / http://localhost:3002/
    ProxyPassReverse / http://localhost:3002/
</VirtualHost>
```
## Mining

denaro uses a PoW system.  

Block hash algorithm is sha256.  
The block sha256 hash must start with the last `difficulty` hex characters of the previously mined block.    
`difficulty` can also have decimal digits, that will restrict the `difficulty + 1`th character of the derived sha to have a limited set of values.    
```python
from math import ceil

difficulty = 6.3
decimal = difficulty % 1

charset = '0123456789abcdef'
count = ceil(16 * (1 - decimal))
allowed_characters = charset[:count]
```

Address must be present in the string in order to ensure block property.  

Blocks have a block reward that will half itself til it reaches 0.  
There will be `150000` blocks with reward `100`, and so on til `0.390625`, which will last `458732` blocks.   
The last block with a reward will be the `458733`th, with a reward of `0.3125`.  
Subsequent blocks won't have a block reward.  
Reward will be added the fees of the transactions included in the block.  
A transaction may also have no fees at all.  

## Dump and Load database

```
$ sudo su postgres
$ pg_dump -d denaro2 > /tmp/file.sql

# load
$ psql -U postgres -d denaro2 < file.sql
```