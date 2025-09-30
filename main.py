from orchestrator.router_client import route

if __name__ == "__main__":
    print(route({"task":"ping","payload":{"msg":"Velu online"}}))
