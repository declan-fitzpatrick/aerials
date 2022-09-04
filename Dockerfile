FROM flashspys/nginx-static
RUN rm -rf /etc/nginx/conf.d/default.conf
COPY nginx-cors.conf /etc/nginx/conf.d/default.conf