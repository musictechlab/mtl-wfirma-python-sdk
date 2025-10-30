format:
	poetry run black .
	poetry run autopep8 --in-place --recursive .

lint:
	poetry run flake8

test:
	poetry run pytest -v

release:
	poetry build
	poetry publish	

ruff:
	poetry run ruff check . --fix
	poetry run ruff format .