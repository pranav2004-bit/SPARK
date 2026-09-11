import hashlib
import urllib3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials

cors_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<CORSConfiguration>
  <CORSRule>
    <AllowedOrigin>*</AllowedOrigin>
    <AllowedMethod>GET</AllowedMethod>
    <AllowedMethod>PUT</AllowedMethod>
    <AllowedMethod>POST</AllowedMethod>
    <AllowedMethod>DELETE</AllowedMethod>
    <AllowedMethod>HEAD</AllowedMethod>
    <AllowedHeader>*</AllowedHeader>
    <ExposeHeader>ETag</ExposeHeader>
    <MaxAgeSeconds>3000</MaxAgeSeconds>
  </CORSRule>
</CORSConfiguration>"""

url = "http://minio:9000/aptlogic?cors"
creds = Credentials("aptlogic_admin", "aptlogic_minio_dev_pass")
payload_hash = hashlib.sha256(cors_xml).hexdigest()

req = AWSRequest(
    method="PUT",
    url=url,
    data=cors_xml,
    headers={
        "Content-Type": "application/xml",
        "x-amz-content-sha256": payload_hash,
    },
)
SigV4Auth(creds, "s3", "us-east-1").add_auth(req)

# Build final headers — drop Content-MD5 if SigV4Auth added it
final_headers = {k: v for k, v in req.headers.items() if k.lower() != "content-md5"}
print("Sending headers:")
for k, v in final_headers.items():
    print(f"  {k}: {v}")

# Use urllib3 (no requests needed)
http = urllib3.PoolManager()
resp = http.request(
    "PUT",
    url,
    body=cors_xml,
    headers=final_headers,
)
print("Status:", resp.status)
print("Body:", resp.data.decode()[:500])
