
all: list fetch

.PHONY: list
list:
	npm run site:www.undocs.org:list

.PHONY: fetch
fetch:
	npm run site:www.undocs.org:fetch
