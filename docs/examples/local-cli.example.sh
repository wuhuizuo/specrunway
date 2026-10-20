specrunway doctor
specrunway plan add-global-rate-limit --store engineering --request request.txt
specrunway run add-global-rate-limit --store engineering
# Inspect the review pack, approve its digest, then continue.
specrunway approve <execution-id> --kind plan
specrunway resume <execution-id>
specrunway status <execution-id>
specrunway approve <execution-id> --kind implementation
specrunway resume <execution-id>
# After the selected completion policy is satisfied:
specrunway archive <execution-id>
