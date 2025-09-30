from typing import Dict, Any
def route(task: Dict[str, Any]) -> Dict[str, Any]:
    # TODO: dispatch to agents/services
    return {'status':'ok','echo':task}
