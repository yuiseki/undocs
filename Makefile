
all: list fetch

.PHONY
list:
	npm run site:www.undocs.org:list

.PHONY
fetch:
	npm run site:www.undocs.org:fetch
