format:
	poetry run black .
	poetry run autopep8 --in-place --recursive .

lint:
	poetry run flake8

test:
	poetry run pytest -v