hub doctor
hub plan add-global-rate-limit --store engineering --request request.txt
hub run add-global-rate-limit --store engineering
# Inspect the review pack, approve its digest, then continue.
hub approve <execution-id> --kind plan
hub resume <execution-id>
hub status <execution-id>
hub approve <execution-id> --kind implementation
hub resume <execution-id>
# After the selected completion policy is satisfied:
hub archive <execution-id>
