# PHP Backend Evidence

Verification: PHPUnit test suite passes (`./vendor/bin/phpunit`), `composer validate` exits 0, `composer audit` shows no vulnerabilities, and a request to a protected endpoint without a valid token returns HTTP 401 with a structured JSON body.
