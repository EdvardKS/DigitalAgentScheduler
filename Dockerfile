# Usar una imagen base de Python
FROM python:3.11

# Establecer el directorio de trabajo
WORKDIR /app

# Copiar el archivo de requisitos y el código fuente
COPY requirements.txt requirements.txt
COPY . .

# Instalar las dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Exponer el puerto que utiliza la app
EXPOSE 5000

# Comando para ejecutar la aplicación
CMD ["flask", "run", "--host=0.0.0.0"]
