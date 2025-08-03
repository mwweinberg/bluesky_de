Traceback (most recent call last):
  File "/root/bluesky_de/bluesky_de.py", line 480, in <module>
    get_usernames()
  File "/root/bluesky_de/bluesky_de.py", line 76, in get_usernames
    list_payload = requests.get(full_api_request_url)
  File "/usr/lib/python3/dist-packages/requests/api.py", line 76, in get
    return request('get', url, params=params, **kwargs)
  File "/usr/lib/python3/dist-packages/requests/api.py", line 61, in request
    return session.request(method=method, url=url, **kwargs)
  File "/usr/lib/python3/dist-packages/requests/sessions.py", line 544, in request  
    resp = self.send(prep, **send_kwargs)
  File "/usr/lib/python3/dist-packages/requests/sessions.py", line 657, in send
    r = adapter.send(request, **kwargs)
  File "/usr/lib/python3/dist-packages/requests/adapters.py", line 516, in send
    raise ConnectionError(e, request=request)
requests.exceptions.ConnectionError: HTTPSConnectionPool(host='public.api.bsky.app', port=443): Max retries exceeded with url: /xrpc/app.bsky.graph.getList?list=at://did:plc:ijife7e4twbh2bnrybnsgpwb/app.bsky.graph.list/3lg424mfsl42l (Caused by NewConnectionError('<urllib3.connection.HTTPSConnection object at 0x7fd29aad85e0>: Failed to establish a new connection: [Errno 101] Network is unreachable'))
