openspec new change add-global-rate-limit --store engineering --json
openspec status --change add-global-rate-limit --store engineering --json
openspec instructions apply --change add-global-rate-limit --store engineering --json
openspec validate add-global-rate-limit --type change --store engineering --strict --json
# Archive only after Hub checks explicit completion approval.
openspec archive add-global-rate-limit --store engineering --yes
