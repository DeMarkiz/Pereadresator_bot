class ProxyManager:
    def __init__(self, proxy_list_file: str):
        try:
            with open(proxy_list_file, 'r', encoding='utf-8') as f:
                proxy_list = f.read().splitlines()
        except Exception as e:
            print(f"Не удалось считать прокси с файла ({e})")
            proxy_list = []
        self.proxies = [
            (3, proxy[0].strip(), int(proxy[1]), True, proxy[2], proxy[3])
            for proxy in list(
                map(lambda x: x.split(':'), proxy_list)
            )
        ]
        self.index = 1
        self.count = len(self.proxies)

    def get_proxy(self):
        self.index += 1
        if self.index >= len(self.proxies):
            self.index = 0
        return self.proxies[self.index] if self.count > 0 else None
