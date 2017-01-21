from .base_classes import RendermanBasePropertyGroup
from bpy.props import *

class RendermanRenderLayerSettings(RendermanBasePropertyGroup):
    ''' When the renderman settings get added to the render layer, this is
    created.  Note these settings are stored in a collection on the scene, 
    since render layers don't take custom properties themselves.'''
    
    # render layer properties

    render_layer = StringProperty()
    #custom_aovs = CollectionProperty(type=RendermanAOV,
    #                                 name='Custom AOVs')
    custom_aov_index = IntProperty(min=-1, default=-1)
    
    object_group = StringProperty(name='Object Group')
    light_group = StringProperty(name='Light Group')

    export_multilayer = BoolProperty(
        name="Export Multilayer",
        description="Enabling this will combine passes and output as a multilayer file",
        default=False)

    exr_format_options = EnumProperty(
        name="EXR Bit Depth",
        description="Sets the bit depth of the .exr file.  Leaving at 'default' will use the Renderman defaults",
        items=[
            ('default',  'Default', ''),
            ('half',  'Half (16 bit)',  ''),
            ('float',  'Float (32 bit)', '')],
        default='default')

    use_deep = BoolProperty(
        name="Use Deep Data",
        description="The output file will contain extra 'deep' information that can aid with compositing.  This can increase file sizes dramatically.  Z channels will automatically be generated so they do not need to be added to the AOV panel",
        default=False)

    exr_compression = EnumProperty(
        name="EXR Compression",
        description="Determined the compression used on the EXR file.  Leaving at 'default' will use the Renderman defaults",
        items=[
            ('default',  'Default',  ''),
            ('none',  'None',  ''),
            ('rle',  'rle',  ''),
            ('zip',  'zip',  ''),
            ('zips',  'zips', ''),
            ('pixar',  'pixar',  ''),
            ('b44', 'b44', ''),
            ('piz',  'piz',  '')],
        default='default')

    exr_storage = EnumProperty(
        name="EXR Storage Mode",
        description="This determines how the EXR file is formatted.  Tile-based may reduce the amount of memory used by the display buffer",
        items=[
            ('scanline', 'Scanline Storage', ''),
            ('tiled', 'Tiled Storage', '')],
        default='scanline')

    ### overrides of base class methods ###
    def to_rib(self, ri, **kwargs):
        '''Uses the custom aovs to create a list of displays '''
        pass

    ### renderlayer specific methods ###
    def simple_to_rib(ri, renderlayer, **kwargs):
        ''' export all the displays for this render layer ''' 
            
        display_driver = kwargs.get('display_driver', 'openexr')
        paths = kwargs.get('paths', {})
        output_files = paths.get('output_files', [])
        aovs_to_denoise = paths.get('aovs_to_denoise', [])

        if 'main_image' in paths:
            # just going to always output rgba
            ri.Display(paths['main_image'], display_driver, "rgba", {})
            output_files.append(paths['main_image'])
        else:
            ri.Display('null', 'null', "rgba", {})

        # rm_rl = self.render_layers.get(render_layer.name, None)

        # # there's no render layer settins
        # if not rm_rl:
        #     RenderLayer.simple_to_rib(ri, render_layer)

        # # else we have custom rman render layer settings
        # else:
        #     rm_rl.to_rib(ri)

        # external_render = kwargs.get('external_render', False)
        # if (self.do_denoise and not external_render or \
        #     self.external_denoise and external_render) and not is_interactive:
        #     # add display channels for denoising
        #     denoise_aovs = [
        #         # (name, declare type/name, source, statistics, filter)
        #         ("Ci", 'color', None, None, None),
        #         ("a", 'float', None, None, None),
        #         ("mse", 'color', 'color Ci', 'mse', None),
        #         ("albedo", 'color',
        #          'color lpe:nothruput;noinfinitecheck;noclamp;unoccluded;overwrite;C(U2L)|O',
        #          None, None),
        #         ("albedo_var", 'color', 'color lpe:nothruput;noinfinitecheck;noclamp;unoccluded;overwrite;C(U2L)|O',
        #          "variance", None),
        #         ("diffuse", 'color', 'color lpe:C(D[DS]*[LO])|O', None, None),
        #         ("diffuse_mse", 'color', 'color lpe:C(D[DS]*[LO])|O', 'mse', None),
        #         ("specular", 'color', 'color lpe:CS[DS]*[LO]', None, None),
        #         ("specular_mse", 'color', 'color lpe:CS[DS]*[LO]', 'mse', None),
        #         ("z", 'float', 'float z', None, True),
        #         ("z_var", 'float', 'float z', "variance", True),
        #         ("normal", 'normal', 'normal Nn', None, None),
        #         ("normal_var", 'normal', 'normal Nn', "variance", None),
        #         ("forward", 'vector', 'vector motionFore', None, None),
        #         ("backward", 'vector', 'vector motionBack', None, None)
        #     ]

        #     for aov, declare_type, source, statistics, do_filter in denoise_aovs:
        #         params = {}
        #         if source:
        #             params['string source'] = source
        #         if statistics:
        #             params['string statistics'] = statistics
        #         if do_filter:
        #             params['string filter'] = rm.pixelfilter
        #         ri.DisplayChannel('%s %s' % (declare_type, aov), params)

        #     # output denoise_data.exr
        #     image_base, ext = main_display.rsplit('.', 1)
        #     ri.Display('+' + image_base + '.variance.exr', 'openexr',
        #                "Ci,a,mse,albedo,albedo_var,diffuse,diffuse_mse,specular,specular_mse,z,z_var,normal,normal_var,forward,backward",
        #                {"string storage": "tiled"})