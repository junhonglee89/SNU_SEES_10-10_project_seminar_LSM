build:
	rm -rf _build
	jupyter-book build .
	open _build/html/index.html