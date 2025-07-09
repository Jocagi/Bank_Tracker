from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, FileField, SubmitField, TextAreaField, validators
from models import Categoria

class UploadForm(FlaskForm):
    banco = StringField('Banco', validators=[validators.DataRequired()])
    tipo_cuenta = StringField('Tipo de Cuenta', validators=[validators.DataRequired()])
    file = FileField('Archivo', validators=[validators.DataRequired()])
    submit = SubmitField('Cargar')

class CategoriaForm(FlaskForm):
    nombre = StringField('Nombre', validators=[validators.DataRequired()])
    submit = SubmitField('Guardar')

class ComercioForm(FlaskForm):
    nombre = StringField('Nombre', validators=[validators.DataRequired()])
    categoria_id = SelectField('Categoría', coerce=int, validators=[validators.DataRequired()])
    reglas = TextAreaField('Reglas (una por línea)')
    submit = SubmitField('Guardar')