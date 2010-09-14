#!/usr/bin/env python
import pdb
import re
from optparse import OptionParser
from app.config import *
from copy import copy, deepcopy
import sys
import os, os.path
import shutil
sys.path.append(APP_ABS_PATH)
import pygtk
pygtk.require('2.0')
import gtk
import gtk.glade
# XML handling
from lxml import etree as ET
#Need to pretty print XML
from xml.dom import minidom
from kmc_generator import ProcessList as ProcListWriter


#Kiwi imports
from kiwi.ui.views import SlaveView, BaseView
from kiwi.controllers import BaseController
import kiwi.ui
from kiwi.ui.delegates import Delegate, SlaveDelegate, ProxyDelegate, ProxySlaveDelegate, GladeDelegate, GladeSlaveDelegate
from kiwi.python import Settable
from kiwi.ui.objectlist import ObjectTree, Column
from kiwi.datatypes import ValidationError

# Canvas Import
from pygtkcanvas.canvas import Canvas
from pygtkcanvas.canvaslayer import CanvasLayer
from pygtkcanvas.canvasitem import *


KMCPROJECT_DTD = '/kmc_project.dtd'
PROCESSLIST_DTD = '/process_list.dtd'
XMLFILE = './default.xml'
SRCDIR = './fortran_src'
GLADEFILE = os.path.join(APP_ABS_PATH, 'kmc_editor2.glade')


class Attributes:
    attributes = []
    def __init__(self, **kwargs):
        for attribute in self.attributes:
            if kwargs.has_key(attribute):
                self.__dict__[attribute] = kwargs[attribute]
        for key in kwargs:
            if key not in self.attributes:
                raise AttributeError, 'Tried to initialize illegal attribute %s' % key
    def __setattr__(self, attrname, value):
        if attrname in self.attributes:
            self.__dict__[attrname] = value
        else:
            raise AttributeError, 'Tried to set illegal attribute %s' % attrname

class CorrectlyNamed:
    def on_name__validate(self, widget, name):
        if ' ' in name:
            return ValidationError('No spaces allowed')
        elif name and not name[0].isalpha():
            return ValidationError('Need to start with a letter')

class Site(Attributes):
    attributes = ['index','name','site_x', 'site_y']
    def __init__(self, **kwargs):
        Attributes.__init__(self, **kwargs)

    def __repr__(self):
        return '%s %s %s %s' % (self.name, self.index, self.site_x, self.site_y)

class Lattice(Attributes, CorrectlyNamed):
    attributes = ['name','unit_cell_size_x','unit_cell_size_y','sites']
    def __init__(self, **kwargs):
        Attributes.__init__(self, **kwargs)
        self.sites = []
        self.name = kwargs['name'] if 'name' in kwargs else ''

    def __repr__(self):
        return "%s %s %s\n\n%s" % (self.name, self.unit_cell_size_x, self.unit_cell_size_y, self.sites)

    def add_site(self, site):
        self.sites.append(site)


class ConditionAction(Attributes):
    attributes = ['species','coord']
    def __init__(self, **kwargs):
        Attributes.__init__(self, **kwargs)

class Species(Attributes):
    attributes = ['name', 'color', 'id']
    def __init__(self, **kwargs):
        Attributes.__init__(self, **kwargs)

class SpeciesList(Settable):
    def __init__(self, **kwargs):
        kwargs['name'] = 'Species'
        Settable.__init__(self, **kwargs)


class ProcessList(Settable):
    def __init__(self, **kwargs):
        kwargs['name'] = 'Processes'
        Settable.__init__(self, **kwargs)

class ParameterList(Settable):
    def __init__(self, **kwargs):
        kwargs['name'] = 'Parameters'
        Settable.__init__(self, **kwargs)


class LatticeList(Settable):
    def __init__(self, **kwargs):
        kwargs['name'] = 'Lattices'
        Settable.__init__(self, **kwargs)


class Parameter(Attributes, CorrectlyNamed):
    attributes = ['name', 'value']
    def __init__(self, **kwargs):
        Attributes.__init__(self, **kwargs)

    def on_name__content_changed(self, text):
        self.project_tree.update(self.process)



class ParameterList(Settable):
    def __init__(self, **kwargs):
        kwargs['name'] = 'Parameters'
        Settable.__init__(self, **kwargs)

class Meta(Settable, object):
    name = 'Meta'
    def __init__(self):
        Settable.__init__(self, email='', author='', debug=0, model_name='', model_dimension = 0)

    def add(self, attrib):
        for key in attrib:
            if key in ['debug', 'model_dimension']:
                self.__setattr__(key, int(attrib[key]))
            else:
                self.__setattr__(key, attrib[key])



class Process(Attributes):
    attributes = ['name','center_site', 'rate_constant','condition_list','action_list']
    def __init__(self, **kwargs):
        Attributes.__init__(self, **kwargs)
        self.condition_list=[]
        self.action_list=[]
        self.center_site = ()

    def add_condition(self, condition):
        self.condition_list.append(condition)

    def add_action(self, action):
        self.action_list.append(action)

class Output():
    def __init__(self):
        self.name = 'Output'



class ProjectTree(SlaveDelegate):
    def __init__(self, parent):
        self.project_data = ObjectTree(Column('name', data_type=str))
        self.set_parent(parent)
        self.meta = self.project_data.append(None,Meta())
        self.meta.add({'model_dimension':2})
        self.lattice_list_iter = self.project_data.append(None, LatticeList())
        self.parameter_list_iter = self.project_data.append(None, ParameterList())
        self.species_list_iter = self.project_data.append(None, SpeciesList())
        self.process_list_iter = self.project_data.append(None, ProcessList())
        self.output_iter = self.project_data.append(None, Output())

        self.filename = ''

        SlaveDelegate.__init__(self, toplevel=self.project_data)

    def update(self, model):
        self.project_data.update(model)

    def get_name(self):
        if self.filename:
            return os.path.basename(self.filename)
        else:
            return 'Untitled'
    def __getattr__(self, attr):
        if attr == 'species_list':
            return self.project_data.get_descendants(self.species_list_iter)
        elif attr == 'lattice_list':
            return self.project_data.get_descendants(self.lattice_list_iter)
        elif attr == 'process_list':
            return self.project_data.get_descendants(self.process_list_iter)
        elif attr == 'parameter_list':
            return self.project_data.get_descendants(self.parameter_list_iter)
        elif attr == 'meta':
            return self.meta
        elif attr == 'append':
            return self.project_data.append
        elif attr == 'expand':
            return self.project_data.expand
        elif attr == 'update':
            return self.project_data.update
        else:
            raise AttributeError, attr

    def __repr__(self):
        return self._get_xml_string()

    def import_xml_file(self,filename):
        self.filename = filename
        xmlparser = ET.XMLParser(remove_comments=True)
        root = ET.parse(filename, parser=xmlparser).getroot()
        dtd = ET.DTD(APP_ABS_PATH + KMCPROJECT_DTD)
        if not dtd.validate(root):
            print(dtd.error_log.filter_from_errors()[0])
            return
        for child in root:
            if child.tag == 'lattice_list':
                for lattice in child:
                    name = lattice.attrib['name']
                    size = [ int(x) for x in lattice.attrib['unit_cell_size'].split() ]
                    lattice_elem = Lattice(name=name, unit_cell_size_x=size[0], unit_cell_size_y=size[1])
                    for site in lattice:
                        index =  int(site.attrib['index'])
                        name = site.attrib['type']
                        coord = [ int(x) for x in site.attrib['coord'].split() ]
                        site_elem = Site(index=index, name=name, site_x=coord[0], site_y=coord[1])
                        lattice_elem.add_site(site_elem)
                    self.project_data.append(self.lattice_list_iter, lattice_elem)
            elif child.tag == 'meta':
                for attrib in ['author','email', 'debug','model_name','model_dimension']:
                    if child.attrib.has_key(attrib):
                        self.meta.add({attrib:child.attrib[attrib]})
            elif child.tag == 'parameter_list':
                for parameter in child:
                    name = parameter.attrib['name']
                    value = parameter.attrib['value']
                    parameter_elem = Settable(name=name,type=type,value=value)
                    self.project_data.append(self.parameter_list_iter, parameter_elem)
            elif child.tag == 'process_list':
                for process in child:
                    center_site = [ int(x) for x in  process.attrib['center_site'].split() ]
                    name = process.attrib['name']
                    rate_constant = process.attrib['rate_constant']
                    process_elem = Process(name=name, center_site=center_site, rate_constant=rate_constant)
                    for sub in process:
                        if sub.tag == 'action' or sub.tag == 'condition':
                            species =  sub.attrib['species']
                            coord = [ int(x) for x in sub.attrib['coord'].split() ]
                            condition_action = ConditionAction(species=species, coord=coord)
                            if sub.tag == 'action':
                                process_elem.add_action(condition_action)
                            elif sub.tag == 'condition':
                                process_elem.add_condition(condition_action)
                    self.project_data.append(self.process_list_iter, process_elem)
            elif child.tag == 'species_list':
                for species in child:
                    name = species.attrib['name']
                    id = species.attrib['id']
                    color = species.attrib['color']
                    species_elem = Species(name=name, color=color, id=id)
                    self.project_data.append(self.species_list_iter, species_elem)
        self.expand_all()
        self.select_meta()
        print(self)

    def expand_all(self):
        self.project_data.expand(self.species_list_iter)
        self.project_data.expand(self.lattice_list_iter)
        self.project_data.expand(self.parameter_list_iter)
        self.project_data.expand(self.process_list_iter)

    def _get_xml_string(self):
        def prettify_xml(elem):
            rough_string = ET.tostring(elem,encoding='utf-8')
            reparsed = minidom.parseString(rough_string)
            return reparsed.toprettyxml(indent='    ')
        # build XML Tree
        root = ET.Element('kmc')
        meta = ET.SubElement(root,'meta')
        if hasattr(self.meta, 'author'):
            meta.set('author', self.meta.author)
        if hasattr(self.meta, 'email'):
            meta.set('email', self.meta.email)
        if hasattr(self.meta, 'model_name'):
            meta.set('model_name', self.meta.model_name)
        if hasattr(self.meta, 'model_dimension'):
            meta.set('model_dimension', str(self.meta.model_dimension))
        if hasattr(self.meta, 'debug'):
            meta.set('debug', str(self.meta.debug))
        species_list = ET.SubElement(root,'species_list')
        for species in self.species_list:
            species_elem = ET.SubElement(species_list,'species')
            species_elem.set('name',species.name)
            species_elem.set('color',species.color)
            species_elem.set('id',str(species.id))
        parameter_list = ET.SubElement(root,'parameter_list')
        for parameter in self.parameter_list:
            parameter_elem = ET.SubElement(parameter_list, 'parameter')
            parameter_elem.set('name', parameter.name)
            parameter_elem.set('value', str(parameter.value))
        lattice_list = ET.SubElement(root, 'lattice_list')
        for lattice in self.lattice_list:
            lattice_elem = ET.SubElement(lattice_list,'lattice')
            size = [lattice.unit_cell_size_x, lattice.unit_cell_size_y ]
            lattice_elem.set('unit_cell_size', str(size)[1 :-1].replace(',',''))
            lattice_elem.set('name', lattice.name)
            for site in lattice.sites:
                site_elem = ET.SubElement(lattice_elem, 'site')
                site_elem.set('index',str(site.index))
                site_elem.set('type',site.name)
                site_elem.set('coord','%s %s' % (site.site_x, site.site_y))
        process_list = ET.SubElement(root, 'process_list')
        for process in self.process_list:
            process_elem = ET.SubElement(process_list,'process')
            process_elem.set('rate_constant', process.rate_constant)
            process_elem.set('name', process.name)
            process_elem.set('center_site', str(process.center_site)[1 :-1].replace(',',''))
            for condition in process.condition_list:
                condition_elem = ET.SubElement(process_elem, 'condition')
                condition_elem.set('species', condition.species)
                condition_elem.set('coord', str(condition.coord)[1 :-1].replace(',', ''))
            for action in process.action_list:
                action_elem = ET.SubElement(process_elem, 'action')
                action_elem.set('species', action.species)
                action_elem.set('coord', str(action.coord)[1 :-1].replace(',',''))
        return prettify_xml(root)

    def select_meta(self):
        self.focus_topmost()
        self.on_project_data__selection_changed(0, self.meta)

    def on_project_data__selection_changed(self, item, elem):
        slave = self.get_parent().get_slave('workarea')
        if slave:
            self.get_parent().detach_slave('workarea')
        if isinstance(elem, Meta):
            meta_form = MetaForm(self.meta)
            self.get_parent().attach_slave('workarea', meta_form)
            meta_form.focus_toplevel()
            meta_form.focus_topmost()
        elif isinstance(elem, Process):
            form = ProcessForm(elem, self.project_data)
            self.get_parent().attach_slave('workarea', form)
            form.focus_topmost()
        elif isinstance(elem, Species):
            form = SpeciesForm(elem, self.project_data)
            self.get_parent().attach_slave('workarea', form)
            form.focus_topmost()
        elif isinstance(elem, Parameter):
            form = ParameterForm(elem, self.project_data)
            self.get_parent().attach_slave('workarea', form)
            form.focus_topmost()
        elif isinstance(elem, Lattice):
            form = LatticeEditor(elem, self.project_data)
            #kiwi.ui.dialogs.warning('Changing lattice retro-actively might break processes.\nYou have been warned.')
            self.get_parent().attach_slave('workarea', form)
            form.on_unit_cell_ok_button__clicked(form.unit_cell_ok_button)
            form.focus_topmost()
        else:
            self.get_parent().toast('Not implemented, yet.')



class ProcessForm(ProxySlaveDelegate, CorrectlyNamed):
    gladefile=GLADEFILE
    toplevel_name='process_form'
    widgets = ['process_name','rate_constant' ]
    def __init__(self, model, project_tree):
        self.model = model
        self.project_tree = project_tree
        ProxySlaveDelegate.__init__(self, model)

    def on_process_name__content_changed(self, text):
        self.project_tree.update(self.model)

    def on_btn_chem_eq__clicked(self, button):
        # get chemical expression from user
        chem_form = gtk.MessageDialog(parent=None, flags=gtk.DIALOG_MODAL, type=gtk.MESSAGE_QUESTION, buttons=gtk.BUTTONS_OK_CANCEL, message_format='Please enter a chemical equation')
        form_entry = gtk.Entry()
        chem_form.vbox.pack_start(form_entry)
        chem_form.vbox.show_all()
        resp = chem_form.run()
        eq = form_entry.get_text()
        chem_form.destroy()


class SiteForm(ProxyDelegate):
    gladefile=GLADEFILE
    toplevel_name='site_form'
    widgets=['site_name','site_index','site_x','site_y']
    def __init__(self, site, parent):
        ProxyDelegate.__init__(self, site)
        self.site = site
        self.parent = parent
        self.site_x.set_value(site.site_x)
        self.site_y.set_value(site.site_y)
        self.site_x.set_sensitive(False)
        self.site_y.set_sensitive(False)
        self.site_index.set_sensitive(False)
        self.show_all()

    def on_site_name__validate(self, widget, site_name):
        # check if other site already has the name
        if  filter(lambda x : x.name == site_name, self.parent.model.sites):
            self.site_ok.set_sensitive(False)
            return ValidationError('Site name needs to be unique')
        else:
            self.site_ok.set_sensitive(True)


    def on_site_ok__clicked(self, button):
        if len(self.site_name.get_text()) == 0 :
            self.parent.model.sites.remove(self.model)
            for node in self.parent.site_layer:
                if node.coord[0] == self.site_x.get_value_as_int() and node.coord[1] == self.site_y.get_value_as_int():
                    node.filled = False
        else:
            for node in self.parent.site_layer:
                if node.coord[0] == self.site_x.get_value_as_int() and node.coord[1] == self.site_y.get_value_as_int():
                    node.filled = True
        self.parent.canvas.redraw()
        self.hide()



class LatticeEditor(ProxySlaveDelegate, CorrectlyNamed):
    """Widget to define a lattice and the unit cell
    """
    gladefile=GLADEFILE
    toplevel_name='lattice_form'
    widgets = ['lattice_name','unit_x','unit_y']
    def __init__(self, lattice, project_tree):
        ProxySlaveDelegate.__init__(self, lattice)
        self.project_tree = project_tree
        self.canvas = Canvas()
        self.canvas.set_flags(gtk.HAS_FOCUS | gtk.CAN_FOCUS)
        self.canvas.grab_focus()
        self.grid_layer = CanvasLayer()
        self.site_layer = CanvasLayer()
        self.canvas.append(self.grid_layer)
        self.canvas.append(self.site_layer)
        self.lattice_pad.add(self.canvas)

        self.unit_cell_ok_button.set_sensitive(False)
        self.on_lattice_name__content_changed(self.lattice_name)

    def on_unit_cell_ok_button__clicked(self, button):
        if button.get_label() == 'gtk-ok':
            X, Y = 400, 400
            button.set_label('Reset')
            button.set_tooltip_text('Delete all sites and start anew')
            x = self.unit_x.get_value_as_int()
            y = self.unit_y.get_value_as_int()
            self.unit_x.set_sensitive(False)
            self.unit_y.set_sensitive(False)
            self.lattice_name.set_sensitive(False)
            self.canvas.show()
            for i in range(x+1):
                lx = CanvasLine(self.grid_layer,  i*(X/x), 0, i*(X/x),Y, bg=(0.,0.,0.))
            for i in range(y+1):
                ly = CanvasLine(self.grid_layer,0 ,i*(Y/y),X, i*(Y/y), bg=(0.,0.,0.))
            for i in range(x+1):
                for j in range(y+1):
                    r = 10
                    o = CanvasOval(self.site_layer, i*(X/x)-r,j*(Y/y)-r,i*(X/x)+r,j*(Y/y)+r, bg=(1.,1.,1.))
                    o.coord = i % x, (y-j) % y
                    o.connect('button-press-event', self.site_press_event)
                    for node in self.model.sites:
                        if node.site_x == o.coord[0] and node.site_y == o.coord[1]:
                            o.filled = True

            self.canvas.move_all(50,50)
        elif button.get_label()=='Reset':
            while self.site_layer:
                self.site_layer.pop()
            while self.grid_layer:
                self.grid_layer.pop()
            button.set_label('gtk-ok')
            button.set_tooltip_text('Add sites')
            self.model.sites = []
            self.unit_x.set_sensitive(True)
            self.unit_y.set_sensitive(True)
            self.lattice_name.set_sensitive(True)

            self.canvas.redraw()
            self.canvas.hide()

    def on_lattice_name__validate(self, widget, lattice_name):
        return self.on_name__validate(widget, lattice_name)

    def on_lattice_name__content_changed(self, widget):
        self.project_tree.update(self.model)
        if  widget.get_text_length() == 0 :
            self.unit_cell_ok_button.set_sensitive(False)
        else:
            self.unit_cell_ok_button.set_sensitive(True)

    def site_press_event(self, widget, item, event):
        if item.filled:
            new_site = filter(lambda x: (x.site_x, x.site_y) == item.coord, self.model.sites)[0]
        else:
            # choose the smallest number that is not given away
            indexes = [x.index for x in self.model.sites]
            for i in range(1,len(indexes)+2):
                if i not in indexes:
                    index = i
                    break
            new_site = Site(site_x=item.coord[0], site_y=item.coord[1], name='', index=index)
            self.model.sites.append(new_site)
        site_form = SiteForm(new_site, self)



class MetaForm(ProxySlaveDelegate, CorrectlyNamed):
    gladefile=GLADEFILE
    toplevel_name='meta_form'
    widgets = ['author','email','model_name','model_dimension','debug']
    def __init__(self, model):
        ProxySlaveDelegate.__init__(self, model)
        self.model_dimension.set_sensitive(False)

    def on_model_name__validate(self, widget, model_name):
        return self.on_name__validate(widget, model_name)

class InlineMessage(SlaveView):
    gladefile=GLADEFILE
    toplevel_name = 'inline_message'
    widgets = ['message_label']
    def __init__(self, message=''):
        SlaveView.__init__(self)
        self.message_label.set_text(message)


class ParameterForm(ProxySlaveDelegate, CorrectlyNamed):
    gladefile=GLADEFILE
    toplevel_name='parameter_form'
    widgets = ['parameter_name', 'value']
    def __init__(self, model, project_tree):
        self.project_tree = project_tree
        ProxySlaveDelegate.__init__(self, model)
        self.name.grab_focus()

    def on_parameter_name__content_changed(self, text):
        self.project_tree.update(self.model)

class SpeciesForm(ProxySlaveDelegate, CorrectlyNamed):
    gladefile=GLADEFILE
    toplevel_name='species_form'
    widgets = ['name', 'color', 'id']
    def __init__(self, model, project_tree):
        self.project_tree = project_tree
        ProxySlaveDelegate.__init__(self, model)
        self.id.set_sensitive(False)
        self.name.grab_focus()

    def on_name__content_changed(self, text):
        self.project_tree.update(self.model)


class KMC_Editor(GladeDelegate):
    widgets = ['workarea','statbar']
    gladefile=GLADEFILE
    toplevel_name='main_window'
    def __init__(self):
        self.project_tree = ProjectTree(parent=self)
        GladeDelegate.__init__(self, delete_handler=self.on_btn_quit__clicked)
        self.attach_slave('overviewtree', self.project_tree)
        self.set_title(self.project_tree.get_name())
        self.project_tree.show()

        self.saved_state = str(self.project_tree)
        # Cast initial message
        self.toast('Start a new project by filling in meta information,\nlattice, species, parameters, and processes or open an existing one\nby opening a kMC XML file')

    def toast(self, toast):
        if self.get_slave('workarea'):
            self.detach_slave('workarea')
        inline_message = InlineMessage(toast)
        self.attach_slave('workarea',inline_message)
        inline_message.show()
    def on_btn_new_project__clicked(self, button):
        if str(self.project_tree) != self.saved_state:
            # if there are unsaved changes, ask what to do first
            save_changes_dialog = gtk.Dialog(buttons=(gtk.STOCK_DISCARD, gtk.RESPONSE_DELETE_EVENT, gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_SAVE, gtk.RESPONSE_OK), title='Saved unsaved changes?')
            save_changes_dialog.vbox.pack_start(gtk.Label("\nThere are unsaved changes.\nWhat shall we do?\n\n"))
            save_changes_dialog.show_all()
            resp = save_changes_dialog.run()
            save_changes_dialog.destroy()
            if resp == gtk.RESPONSE_DELETE_EVENT:
                # nothing to do here
                pass
            elif resp == gtk.RESPONSE_CANCEL:
                return
            elif resp == gtk.RESPONSE_OK:
                self.on_btn_save_model__clicked(None)
        self.project_tree = ProjectTree(parent=self)
        if self.get_slave('overviewtree'):
            self.detach_slave('overviewtree')
        self.attach_slave('overviewtree', self.project_tree)
        self.set_title(self.project_tree.get_name())
        self.project_tree.show()
        self.toast('Start a new project by filling in meta information,\nlattice, species, parameters, and processes or open an existing one\nby opening a kMC XML file')

    def on_btn_add_lattice__clicked(self, button):
        new_lattice = Lattice()
        self.project_tree.append(self.project_tree.lattice_list_iter, new_lattice)
        lattice_form = LatticeEditor(new_lattice, self.project_tree)
        self.project_tree.expand(self.project_tree.lattice_list_iter)
        if self.get_slave('workarea'):
            self.detach_slave('workarea')
        self.attach_slave('workarea', lattice_form)
        lattice_form.focus_topmost()

    def on_btn_add_species__clicked(self, button):
        new_species = Species(color='#fff', name='')
        self.project_tree.append(self.project_tree.species_list_iter, new_species)
        self.project_tree.expand(self.project_tree.species_list_iter)
        new_species.id = "%s" % (len(self.project_tree.species_list))
        species_form = SpeciesForm(new_species, self.project_tree)
        if self.get_slave('workarea'):
            self.detach_slave('workarea')
        self.attach_slave('workarea', species_form)
        species_form.focus_topmost()

    def on_btn_add_process__clicked(self, button):
        new_process = Process(name='', rate_constant='')
        self.project_tree.append(self.project_tree.process_list_iter, new_process)
        self.project_tree.expand(self.project_tree.process_list_iter)
        process_form = ProcessForm(new_process, self.project_tree)
        if self.get_slave('workarea'):
            self.detach_slave('workarea')
        self.attach_slave('workarea', process_form)
        process_form.focus_topmost()

    def on_btn_add_parameter__clicked(self, button):
        new_parameter = Parameter(name='', value='')
        self.project_tree.append(self.project_tree.parameter_list_iter, new_parameter)
        self.project_tree.expand(self.project_tree.parameter_list_iter)
        parameter_form = ParameterForm(new_parameter, self.project_tree)
        if self.get_slave('workarea'):
            self.detach_slave('workarea')
        self.attach_slave('workarea', parameter_form)
        parameter_form.focus_topmost()

    def on_btn_open_model__clicked(self, button):
        """Import project from XML
        """
        if str(self.project_tree) != self.saved_state:
            # if there are unsaved changes, ask what to do first
            save_changes_dialog = gtk.Dialog(buttons=(gtk.STOCK_DISCARD, gtk.RESPONSE_DELETE_EVENT, gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_SAVE, gtk.RESPONSE_OK), title='Saved unsaved changes?')
            save_changes_dialog.vbox.pack_start(gtk.Label("\nThere are unsaved changes.\nWhat shall we do?\n\n"))
            save_changes_dialog.show_all()
            resp = save_changes_dialog.run()
            save_changes_dialog.destroy()
            if resp == gtk.RESPONSE_DELETE_EVENT:
                # nothing to do here
                pass
            elif resp == gtk.RESPONSE_CANCEL:
                return
            elif resp == gtk.RESPONSE_OK:
                self.on_btn_save_model__clicked(None)

        # choose which file to open next
        filechooser = gtk.FileChooserDialog(title='Open Project',
            action = gtk.FILE_CHOOSER_ACTION_OPEN,
            buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_OK, gtk.RESPONSE_OK ))
        resp = filechooser.run()
        filename = filechooser.get_filename()
        filechooser.destroy()
        if resp == gtk.RESPONSE_OK and filename:
            # Initialize blank project tree
            self.project_tree = ProjectTree(parent=self)
            if self.get_slave('overviewtree'):
                self.detach_slave('overviewtree')
            self.attach_slave('overviewtree', self.project_tree)
            self.set_title(self.project_tree.get_name())
            self.project_tree.show()
            # Import
            self.project_tree.import_xml_file(filename)
            self.set_title(self.project_tree.get_name())
            self.statbar.push(1,'Imported model %s' % self.project_tree.meta.model_name)
            self.saved_state = str(self.project_tree)

    def on_btn_save_model__clicked(self, button, force_save=False):
        #Write Out XML File
        xml_string = str(self.project_tree)
        if xml_string == self.saved_state and not force_save:
            self.statbar.push(1, 'Nothing to save')
        else:
            if not self.project_tree.filename:
                self.on_btn_save_as__clicked(None)
            outfile = open(self.project_tree.filename,'w')
            outfile.write(xml_string)
            outfile.write('<!-- This is an automatically generated XML file, representing a kMC model ' + \
                            'please do not change this unless you know what you are doing -->\n')
            outfile.close()
            self.saved_state = xml_string
            self.statbar.push(1,'Saved %s' % self.project_tree.filename)


    def on_btn_save_as__clicked(self, button):
        filechooser = gtk.FileChooserDialog(title='Save Project As ...',
            action = gtk.FILE_CHOOSER_ACTION_SAVE,
            parent=None,
            buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_OK, gtk.RESPONSE_OK ))
        filechooser.set_property('do-overwrite-confirmation',True)
        resp = filechooser.run()
        if resp == gtk.RESPONSE_OK:
            self.project_tree.filename = filechooser.get_filename()
            self.on_btn_save_model__clicked(None, force_save=True)
        filechooser.destroy()

    def on_btn_export_src__clicked(self, button):
        self.toast('"Export Source" is not implemented, yet.')

    def on_btn_help__clicked(self, button):
        self.toast('"Help" is not implemented, yet.')


    def on_btn_quit__clicked(self, button, *args):
        if self.saved_state != str(self.project_tree):
            save_changes_dialog = gtk.Dialog(buttons=(gtk.STOCK_DISCARD, gtk.RESPONSE_DELETE_EVENT, gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_SAVE, gtk.RESPONSE_OK), title='Saved unsaved changes?')
            save_changes_dialog.vbox.pack_start(gtk.Label("\nThere are unsaved changes.\nWhat shall we do?\n\n"))
            save_changes_dialog.show_all()
            resp = save_changes_dialog.run()
            save_changes_dialog.destroy()
            if resp == gtk.RESPONSE_CANCEL:
                return True
            elif resp == gtk.RESPONSE_DELETE_EVENT:
                self.hide_and_quit()
                gtk.main_quit()
            elif resp == gtk.RESPONSE_OK:
                self.on_btn_save_model__clicked(None)
                self.hide_and_quit()
                gtk.main_quit()
        else:
            self.hide_and_quit()
            gtk.main_quit()
        # Need to return true, or otherwise the window manager destroys 
        # the windows anywas
        return True







if __name__ == '__main__':
    editor = KMC_Editor()
    editor.show_and_loop()
