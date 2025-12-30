from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, FileField, SubmitField, TextAreaField, validators
from wtforms import DecimalField, DateField, BooleanField

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


class RuleForm(FlaskForm):
    categoria_id = SelectField('Categoría', coerce=int, validators=[validators.DataRequired()])
    tipo = SelectField('Tipo', choices=[('fijo', 'Fijo'), ('variable', 'Variable'), ('inesperado', 'Inesperado')], default='inesperado')
    monto = DecimalField('Monto', places=2, rounding=None, validators=[validators.DataRequired()])
    fecha_inicio = DateField('Fecha inicio', format='%Y-%m-%d', validators=[validators.DataRequired()])
    submit = SubmitField('Guardar')


class PlanForm(FlaskForm):
    nombre = StringField('Nombre', validators=[validators.DataRequired()])
    fecha_inicio = DateField('Fecha inicio', format='%Y-%m-%d', validators=[validators.DataRequired()])
    active = BooleanField('Activo')
    submit = SubmitField('Guardar')