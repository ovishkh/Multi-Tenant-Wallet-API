.PHONY: run test migrate makemigrations format lint docker-up docker-down shell

run:
	python manage.py runserver 0.0.0.0:8000

test:
	pytest wallets/tests/

migrate:
	python manage.py migrate

makemigrations:
	python manage.py makemigrations

format:
	black .

lint:
	flake8 .

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down

shell:
	python manage.py shell
