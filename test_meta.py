import resdk
from resdk.tables import QCTables

res = resdk.Resolwe(url="https://qa.genialis.io")
res.login()

collection = res.collection.get("validation-run-208")
qt = QCTables(collection=collection)

qt.meta
